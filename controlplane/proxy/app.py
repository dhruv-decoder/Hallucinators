"""The Tower -- FastAPI application wiring the oversight engine behind an OpenAI-compatible gateway.

Endpoints fall into two groups:

*OpenAI-compatible* (so any OpenAI client works with a one-line ``base_url`` swap):
  - ``GET  /v1/models``            -- advertise the served model id(s).
  - ``POST /v1/chat/completions``  -- oversee a completion; supports ``stream=true`` with mid-stream abort.

*Oversight API* (consumed by the Control-Tower dashboard):
  - ``GET  /v1/oversight/summary``          -- P&L totals, action counts, %-cleared-at-T0, thermostat, chain.
  - ``GET  /v1/oversight/receipts``         -- recent hash-chained receipts (full VoI trace).
  - ``GET  /v1/oversight/receipts/{id}``    -- one receipt by id.
  - ``GET  /v1/oversight/stream``           -- Server-Sent Events feed of receipts as they are recorded.
  - ``POST /v1/oversight/policy``           -- switch the active use-case policy profile live.
  - ``POST /v1/oversight/simulate``         -- fire the scripted demo workload through the real pipeline.
  - ``POST /v1/oversight/replay``           -- What-If: re-run a workload under several policies (proof engine).
  - ``GET  /``                              -- the single-file Control-Tower dashboard.

The app holds one :class:`OversightService` for its lifetime. It runs fully offline by default.
"""

from __future__ import annotations

import asyncio
import json
import queue
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse

from controlplane.cascade.detectors.responsibility import RegexPiiDetector
from controlplane.core.types import RequestContext
from controlplane.proxy.openai_schemas import (
    ChatCompletionRequest,
    OversightBlock,
    chat_completion_chunk,
    chat_completion_response,
)
from controlplane.proxy.oversight import OverseeResult, OversightService
from controlplane.proxy.upstream import Generation, build_upstream

_STATIC = Path(__file__).parent / "static"


def _oversight_block(res: OverseeResult) -> OversightBlock:
    """Compress an OverseeResult into the ``controlplane`` block returned on every completion."""
    return OversightBlock(
        action=res.applied.action,
        receipt_id=res.receipt.request_id,
        per_axis_p_fail={ax: round(o.p_fail, 4) for ax, o in res.receipt.per_axis.items()},
        modified=res.applied.modified,
        stopping_reason=res.receipt.stopping_reason,
        net_usd=round(res.receipt.pnl.net_usd, 6),
        added_latency_ms=round(res.added_latency_ms, 2),
        policy_id=res.receipt.policy_id,
    )


def create_app(recorder_path: str | None = "recorder_log.jsonl", force_simulated: bool = False) -> FastAPI:
    """Build the FastAPI app. ``force_simulated`` pins the offline upstream even if a provider key is set."""
    app = FastAPI(title="ControlPlane — The Tower", version="0.1.0")
    service = OversightService(recorder_path=recorder_path)
    upstream = build_upstream(force_simulated=force_simulated)
    app.state.service = service
    app.state.upstream = upstream

    # ---- OpenAI-compatible surface -----------------------------------------------------------------
    @app.get("/v1/models")
    def list_models() -> dict:
        return {
            "object": "list",
            "data": [
                {"id": "controlplane-sim", "object": "model", "owned_by": "controlplane"},
                {"id": upstream.name, "object": "model", "owned_by": "controlplane"},
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        prompt = req.last_user_prompt()
        # Get the candidate from the upstream, then let the caller's own retrieved_context/samples override
        # what the simulator supplied (a real RAG app passes its sources; the simulator fills them in).
        gen = upstream.generate(prompt, req.model, use_case=req.use_case)
        if req.retrieved_context:
            gen.retrieved_context = req.retrieved_context
        if req.samples:
            gen.samples = req.samples
        if req.use_case:
            gen.use_case = req.use_case

        if req.stream:
            return StreamingResponse(
                _stream_completion(service, gen, prompt, req.model),
                media_type="text/event-stream",
            )

        res = await asyncio.to_thread(service.oversee, prompt, gen)
        payload = chat_completion_response(
            text=res.final_text,
            model=req.model,
            oversight=_oversight_block(res),
            prompt_tokens=gen.input_tokens,
            completion_tokens=gen.output_tokens,
        )
        return JSONResponse(payload)

    # ---- Oversight API (for the dashboard) ---------------------------------------------------------
    @app.get("/v1/oversight/summary")
    def summary() -> dict:
        return service.summary()

    @app.get("/v1/oversight/receipts")
    def receipts(limit: int = 50) -> dict:
        recent = service.recorder.receipts[-limit:][::-1]
        return {"receipts": [r.model_dump(mode="json") for r in recent]}

    @app.get("/v1/oversight/receipts/{request_id}")
    def receipt(request_id: str) -> dict:
        for r in reversed(service.recorder.receipts):
            if r.request_id == request_id:
                return r.model_dump(mode="json")
        raise HTTPException(status_code=404, detail="receipt not found")

    @app.get("/v1/oversight/stream")
    async def stream(request: Request):
        return StreamingResponse(
            _receipt_events(service, request), media_type="text/event-stream"
        )

    @app.post("/v1/oversight/policy")
    async def set_policy(request: Request) -> dict:
        body = await request.json()
        key = body.get("policy")
        try:
            service.set_policy(key)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"unknown policy: {key}") from exc
        return {"active_policy": service.policy.id}

    @app.post("/v1/oversight/simulate")
    async def simulate() -> dict:
        """Fire the scripted demo workload through the real pipeline (the UI's 'Send demo traffic' button)."""
        from controlplane.proxy.workload import demo_prompts

        produced = []
        for p in demo_prompts():
            gen = upstream.generate(p["prompt"], p.get("model", "controlplane-sim"), use_case=p.get("use_case"))
            res = await asyncio.to_thread(service.oversee, p["prompt"], gen)
            produced.append({"request_id": res.receipt.request_id, "action": res.applied.action.value})
        return {"processed": len(produced), "results": produced}

    @app.post("/v1/oversight/replay")
    async def replay(request: Request) -> dict:
        """What-If: re-run the recorded workload under several policies -> residual risk vs net cost."""
        from controlplane.proxy.workload import replay_summary

        return await asyncio.to_thread(replay_summary)

    @app.post("/v1/oversight/agent-demo")
    async def agent_demo() -> dict:
        """Run the compounding-hallucination agent trajectory under the trajectory auditor."""
        return await asyncio.to_thread(service.run_agent_demo)

    @app.get("/v1/oversight/compliance")
    def compliance() -> dict:
        """Map the recorded receipts to EU AI Act / ISO 42001 / NIST AI RMF controls (JSON)."""
        from controlplane.compliance import generate_pack

        return generate_pack(
            service.recorder.receipts, service.recorder.verify_chain(), policy_id=service.policy.id
        )

    @app.get("/v1/oversight/compliance.md")
    def compliance_md() -> PlainTextResponse:
        """The same evidence pack rendered as a downloadable Markdown document."""
        from controlplane.compliance import generate_pack, render_markdown

        pack = generate_pack(
            service.recorder.receipts, service.recorder.verify_chain(), policy_id=service.policy.id
        )
        return PlainTextResponse(
            render_markdown(pack),
            headers={"Content-Disposition": "attachment; filename=controlplane_compliance_pack.md"},
        )

    # ---- Dashboard ---------------------------------------------------------------------------------
    @app.get("/")
    def dashboard() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "upstream": upstream.name}

    return app


# ---- streaming helpers -----------------------------------------------------------------------------
_ABORT_PII = RegexPiiDetector()


def _stream_completion(service: OversightService, gen: Generation, prompt: str, model: str):
    """Stream the candidate token-by-token with a mid-stream abort guard.

    The subtlety of a real streaming guard: you must catch a leak *before* the leaked tokens leave. A card
    number streamed word-by-word is only recognisable once all its digits have arrived, so we **hold back
    digit-bearing tokens** in a buffer and only release them once the accumulated text proves safe. If the
    buffered run instead trips the block threshold (a real card / SSN / Aadhaar), we abort: the held tokens
    are discarded (never sent) and a block notice is emitted. Clean text streams with no delay. This is the
    StreamGuard pattern -- predict-and-stop a bad generation rather than only judging it after the fact.

    Softer actions (escalate / annotate / auto-repair) can't be un-sent mid-stream, so they are applied on
    the non-streaming path; the streaming guard is the hard, block-level abort. Stated honestly, not oversold.
    """
    block = service.policy.block_threshold
    accumulated = ""
    hold: list[str] = []
    aborted = False
    chunk_id = None

    for i, word in enumerate(gen.text.split(" ")):
        piece = word if i == 0 else " " + word
        accumulated += piece
        probe = _ABORT_PII.assess(RequestContext(request_id="stream", response=accumulated))[0]
        if probe >= block:
            aborted = True  # the buffered digit run just completed a real identifier -> stop before sending
            break
        if any(ch.isdigit() for ch in word):
            hold.append(piece)  # risky numeric token: withhold until the run is proven safe
        elif hold:
            hold.append(piece)  # a non-digit boundary ends a safe numeric run -> release it whole
            yield _sse(chat_completion_chunk("".join(hold), model, chunk_id=chunk_id))
            hold = []
        else:
            yield _sse(chat_completion_chunk(piece, model, chunk_id=chunk_id))
    if not aborted and hold:  # trailing safe numbers (e.g. "$25") that never tripped the guard
        yield _sse(chat_completion_chunk("".join(hold), model, chunk_id=chunk_id))

    # Finalise with the full pipeline (records the receipt, books P&L) against the true, untruncated response.
    res = service.oversee(prompt, gen)
    if aborted:
        yield _sse(chat_completion_chunk("\n\n[ControlPlane aborted this response] " + res.final_text,
                                         model, chunk_id=chunk_id))
    yield _sse(chat_completion_chunk(None, model, finish_reason="stop", oversight=_oversight_block(res)))
    yield "data: [DONE]\n\n"


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


async def _receipt_events(service: OversightService, request: Request):
    """SSE generator: send a snapshot of recent receipts, then push each new one as it is recorded."""
    q = service.subscribe()
    try:
        # Initial snapshot so a freshly-opened dashboard isn't empty.
        for r in service.recorder.receipts[-20:]:
            yield _sse({"type": "receipt", "receipt": r.model_dump(mode="json")})
        yield _sse({"type": "summary", "summary": service.summary()})
        while True:
            if await request.is_disconnected():
                break
            try:
                receipt = await asyncio.to_thread(q.get, True, 1.0)
                yield _sse({"type": "receipt", "receipt": receipt.model_dump(mode="json")})
                yield _sse({"type": "summary", "summary": service.summary()})
            except queue.Empty:
                yield ": keep-alive\n\n"  # comment frame keeps the connection open
    finally:
        service.unsubscribe(q)
