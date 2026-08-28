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
import os
import queue
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from controlplane.cascade.detectors.responsibility import RegexPiiDetector
from controlplane.core.types import RequestContext
from controlplane.startup import ModelWarmup, env_bool
from controlplane.proxy.openai_schemas import (
    ChatCompletionRequest,
    OversightBlock,
    chat_completion_chunk,
    chat_completion_response,
)
from controlplane.proxy.oversight import OverseeResult, OversightService
from controlplane.proxy.upstream import Generation, build_upstream

_STATIC = Path(__file__).parent / "static"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(min(int(os.environ.get(name, default)), maximum), minimum)
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(min(float(os.environ.get(name, default)), maximum), minimum)
    except ValueError:
        return default



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
    service = OversightService(recorder_path=recorder_path)
    upstream = build_upstream(force_simulated=force_simulated)
    service.upstream = upstream  # lets bulk-simulate jobs generate candidates

    warmup = ModelWarmup(enabled=env_bool("CONTROLPLANE_WARMUP", False))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = warmup.start(service=service)
        try:
            yield
        finally:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="ControlPlane — The Tower", version="0.1.0", lifespan=lifespan)
    # Allow a separately-hosted frontend (e.g. the Next.js app on Vercel) to call the API. Lock this down
    # with CONTROLPLANE_CORS_ORIGINS in production; defaults open for the demo.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("CONTROLPLANE_CORS_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Concurrency admission control now lives on the service (service.max_concurrency / queue_timeout_ms).
    queue_timeout_ms = _env_int("CONTROLPLANE_QUEUE_TIMEOUT_MS", 250, 10, 60_000)
    upstream_timeout_s = _env_float("CONTROLPLANE_UPSTREAM_TIMEOUT_S", 30.0, 0.1, 300.0)
    upstream_retries = _env_int("CONTROLPLANE_UPSTREAM_RETRIES", 1, 0, 3)
    app.state.service = service
    app.state.upstream = upstream
    app.state.runtime_config = {
        "max_concurrency": service.max_concurrency,
        "queue_timeout_ms": service.queue_timeout_ms,
        "upstream_timeout_s": upstream_timeout_s,
        "upstream_retries": upstream_retries,
    }
    app.state.warmup = warmup

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
    async def chat_completions(req: ChatCompletionRequest, request: Request):
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        prompt = req.last_user_prompt()

        acquired = await asyncio.to_thread(service.acquire_request_slot, queue_timeout_ms)
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail="ControlPlane is busy; retry shortly",
                headers={"Retry-After": "1"},
            )

        service.runtime.request_started()
        stream_handoff = False
        try:
            # Route-down (P0.2) + cache (P0.3) on the main path: for a simple prompt on a flagship, actually
            # call a cheaper model; a repeated request reuses the stored generation and skips the upstream.
            from controlplane.cascade.detectors.cost import suggest_route_down

            ctx_str = "\n".join(req.retrieved_context) if req.retrieved_context else None
            routed_to = suggest_route_down(req.model, prompt) if req.model else None
            actual_model = routed_to or req.model
            cache_key = service.cache_key(prompt, req.model, ctx_str, req.use_case, service.policy_for(req.use_case)[1].id)

            def _gen():
                for attempt in range(upstream_retries + 1):
                    try:
                        return upstream.generate(prompt, actual_model, req.use_case)
                    except Exception:  # noqa: BLE001 - retried; re-raised on the last attempt
                        if attempt >= upstream_retries:
                            service.runtime.record_error()
                            raise
                        time.sleep(0.05 * (attempt + 1))
                raise RuntimeError("upstream generation failed")

            gen, cache_hit = await asyncio.wait_for(
                asyncio.to_thread(
                    service.generate_cached,
                    cache_key,
                    _gen,
                    prompt=prompt,
                    model=req.model,
                    context=ctx_str,
                    use_case=req.use_case,
                    policy_id=service.policy_for(req.use_case)[1].id,
                ),
                timeout=upstream_timeout_s * (upstream_retries + 2),
            )
            if routed_to and not cache_hit:
                service.route_down_events += 1

            if req.retrieved_context:
                gen.retrieved_context = req.retrieved_context
            if req.samples:
                gen.samples = req.samples
            if req.use_case:
                gen.use_case = req.use_case

            if req.stream:
                stream_handoff = True
                async def guarded_stream():
                    try:
                        for chunk in _stream_completion(service, gen, prompt, req.model, request_id=request_id):
                            yield chunk
                    finally:
                        service.runtime.request_finished()
                        service.release_request_slot()

                return StreamingResponse(
                    guarded_stream(),
                    media_type="text/event-stream",
                    headers={"X-Request-ID": request_id},
                )

            res = await asyncio.to_thread(service.oversee, prompt, gen, request_id)
            payload = chat_completion_response(
                text=res.final_text,
                model=req.model,
                oversight=_oversight_block(res),
                prompt_tokens=gen.input_tokens,
                completion_tokens=gen.output_tokens,
            )
            response = JSONResponse(payload, headers={"X-Request-ID": res.receipt.request_id})
            return response
        except HTTPException:
            raise
        except Exception as exc:
            service.runtime.record_error()
            raise HTTPException(status_code=502, detail=f"upstream/oversight failure: {exc}") from exc
        finally:
            if not stream_handoff:
                service.runtime.request_finished()
                service.release_request_slot()

    # ---- Oversight API (for the dashboard) ---------------------------------------------------------
    @app.get("/v1/oversight/observability")
    def observability() -> dict:
        data = service.runtime.snapshot()
        data["config"] = dict(app.state.runtime_config)
        return data

    @app.get("/v1/oversight/receipts/{request_id}/verify")
    def verify_receipt(request_id: str) -> dict:
        for r in reversed(service.recorder.receipts):
            if r.request_id == request_id:
                from controlplane.recorder.receipt import compute_hash
                return {
                    "request_id": request_id,
                    "receipt_valid": compute_hash(r) == r.hash_self,
                    "chain_valid": service.recorder.verify_chain(),
                    "hash_self": r.hash_self,
                    "hash_prev": r.hash_prev,
                }
        raise HTTPException(status_code=404, detail="receipt not found")

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        status = warmup.snapshot()
        payload = {
            "ready": bool(status["ready"] and service.policies and service.recorder is not None),
            "upstream": upstream.name,
            "policy_loaded": bool(service.policies),
            "recorder": service.recorder is not None,
            "warmup": status,
        }
        return JSONResponse(payload, status_code=200 if payload["ready"] else 503)

    @app.post("/v1/oversight/jobs/runtime-probe")
    def runtime_probe(n: int = 120, concurrency: int = 16) -> dict:
        return service.start_runtime_probe(n=n, concurrency=concurrency).snapshot()

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

    @app.post("/v1/oversight/policy/generate")
    async def generate_policy(request: Request) -> dict:
        """Generate a tuned oversight policy + projection from a use-case spec; ?apply=1 activates it live."""
        body = await request.json()
        apply = str(body.pop("apply", request.query_params.get("apply", "0"))).lower() in ("1", "true", "yes")
        return service.generate_policy(body, apply=apply)

    @app.post("/v1/oversight/playground")
    async def playground(request: Request) -> dict:
        """Oversee a REAL model response to an arbitrary prompt (+ optional context) -- the live 'try it' path."""
        from controlplane.proxy.upstream import GroqUpstream

        body = await request.json()
        prompt = (body.get("prompt") or "").strip()
        context = (body.get("context") or "").strip() or None
        model = body.get("model") or None
        use_case = body.get("use_case") or "playground"
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")

        # Real route-down: for a simple prompt on a flagship, actually call a cheaper model (not just book an
        # estimate). ``actual_model`` is what gets invoked; the flagship cost becomes the avoided counterfactual.
        from controlplane.cascade.detectors.cost import suggest_route_down
        from controlplane.pnl.pricing import Pricing

        routed_to = suggest_route_down(model, prompt) if model else None
        actual_model = routed_to or model

        def _generate():
            if GroqUpstream.available():
                try:
                    return GroqUpstream().generate(prompt, actual_model, use_case, context)
                except Exception:  # noqa: BLE001 - fall back to the offline upstream if the API call fails
                    pass
            g = upstream.generate(prompt, actual_model or "controlplane-sim", use_case=use_case)
            if context:
                g.retrieved_context = [context]
            return g

        # Real cache bypass: a repeated (prompt, model, context) reuses the stored generation and never calls
        # the upstream again -- the counters below prove it. Keyed on the *requested* model.
        key = service.cache_key(prompt, model, context, use_case, service.policy_for(use_case)[1].id)
        gen, cache_hit = await asyncio.to_thread(
            service.generate_cached,
            key,
            _generate,
            prompt=prompt,
            model=model,
            context=context,
            use_case=use_case,
            policy_id=service.policy_for(use_case)[1].id,
        )
        if routed_to and not cache_hit:
            service.route_down_events += 1
        source = "cache" if cache_hit else ("groq" if getattr(gen, "token_source", "") == "measured" else "simulated")

        res = await asyncio.to_thread(service.oversee, prompt, gen)
        pnl = res.receipt.pnl
        avoided_flagship = 0.0
        if routed_to and not cache_hit:
            pr = Pricing()
            avoided_flagship = round(
                pr.cost(model, gen.input_tokens, gen.output_tokens)
                - pr.cost(actual_model, gen.input_tokens, gen.output_tokens), 6,
            )
        return {
            "source": source,
            "model": gen.model,
            "candidate": gen.text,
            "final": res.final_text,
            "modified": res.applied.modified,
            "cache_hit": cache_hit,
            "routed_down": bool(routed_to and not cache_hit),
            "requested_model": model,
            "served_by": gen.model,
            "economics": {
                "input_tokens": gen.input_tokens,
                "output_tokens": gen.output_tokens,
                "token_source": pnl.token_source,  # "measured" on the real Groq path, else "estimated"
                "model_cost_usd": 0.0 if cache_hit else round(pnl.model_cost_usd, 6),  # a hit spends $0 on the model
                "model_cost_avoided_usd": round(pnl.model_cost_usd, 6) if cache_hit else 0.0,
                "route_down_avoided_flagship_usd": avoided_flagship,  # measured cheaper vs counterfactual flagship
                "cost_saved_usd": round(pnl.cost_saved_usd, 6),
                "safety_spend_usd": round(pnl.safety_spend_usd, 6),
                "net_oversight_usd": round(pnl.net_usd, 6),
                "upstream_calls": service.upstream_calls,
                "cache_hits": service.cache_hits,
                "route_down_events": service.route_down_events,
            },
            "controlplane": _oversight_block(res).model_dump(mode="json"),
            "receipt": res.receipt.model_dump(mode="json"),
        }

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

    @app.post("/v1/oversight/jobs/benchmark")
    def start_benchmark(n: int = 2000, weekly_volume: int = 50_000) -> dict:
        """Start the latency/throughput benchmark; poll GET /v1/oversight/jobs/{id} for progress + result."""
        return service.start_benchmark(n=n, weekly_volume=weekly_volume).snapshot()

    @app.post("/v1/oversight/jobs/simulate")
    def start_bulk_simulate(n: int = 40) -> dict:
        """Start a large simulated workload through the real pipeline (feeds the live feed + P&L)."""
        return service.start_bulk_simulate(n=n).snapshot()

    @app.get("/v1/oversight/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        job = service.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.snapshot()

    @app.get("/v1/oversight/cache")
    def cache_status() -> dict:
        """Expose bounded semantic-cache configuration and measured hit/miss counters."""
        return {
            **service.semantic_cache.stats(),
            "upstream_calls": service.upstream_calls,
            "cache_hits": service.cache_hits,
            "exact_cache_hits": service.exact_cache_hits,
            "semantic_cache_hits": service.semantic_cache_hits,
            "cache_misses": service.cache_misses,
        }

    @app.get("/v1/oversight/informativeness")
    def informativeness() -> dict:
        """Return the empirical-eta artifact status and values currently used by the runtime."""
        return service.informativeness_status()

    @app.get("/v1/oversight/conformal")
    def conformal() -> dict:
        """Return offline conformal risk certificates; prefer a real public-data artifact over the demo seed."""
        artifact = Path(os.environ.get("CONTROLPLANE_CONFORMAL_ARTIFACT", "artifacts/conformal_performance.json"))
        if artifact.exists():
            try:
                return json.loads(artifact.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - fall back to the deterministic demo certificate
                pass

        from controlplane.cascade.conformal import risk_controlled_threshold
        from controlplane.core.types import Axis, PolicyProfile
        from controlplane.demo.run_demo import build_engine
        from controlplane.eval.dataset import synthetic_labeled_dataset

        engine = build_engine(PolicyProfile(id="conformal@eval"), use_models=False)
        scores: list[float] = []
        labels: list[bool] = []
        for ex in synthetic_labeled_dataset():
            outcome = engine.run(ex.ctx).per_axis.get(Axis.PERFORMANCE)
            scores.append(outcome.p_fail if outcome else 0.0)
            labels.append(bool(ex.labels.get(Axis.PERFORMANCE, False)))
        certs = []
        for alpha in (0.30, 0.20, 0.10):
            c = risk_controlled_threshold(scores, labels, alpha)
            certs.append({
                "alpha": alpha, "valid": c.valid, "tau": round(c.tau, 4),
                "empirical_fnr": round(c.empirical_fnr, 4), "risk_bound": round(c.risk_bound, 4),
                "n_failures": c.n_failures, "statement": c.statement(),
            })
        return {"axis": "performance", "source": "synthetic_demo", "certificates": certs}

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

    @app.get("/healthz")
    def healthz() -> dict:
        from controlplane.cascade.detectors.factory import active_models

        return {"ok": True, "upstream": upstream.name, "models": active_models()}

    # ---- Dashboards --------------------------------------------------------------------------------
    # The lite (framework-free) dashboard is always available; the Next.js product UI is served at / when
    # it has been built (web/out) -- so a single service can ship the polished frontend + the API together.
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.get("/lite")
    def lite_dashboard() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    # Mounted LAST so the catch-all never shadows the API routes above.
    web_out = Path(__file__).resolve().parents[2] / "web" / "out"
    if web_out.exists():
        app.mount("/", StaticFiles(directory=str(web_out), html=True), name="webapp")
    else:

        @app.get("/")
        def dashboard() -> FileResponse:
            return FileResponse(_STATIC / "index.html")

    return app


# ---- streaming helpers -----------------------------------------------------------------------------
_ABORT_PII = RegexPiiDetector()


def _stream_completion(
    service: OversightService, gen: Generation, prompt: str, model: str, request_id: str | None = None
):
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
    res = service.oversee(prompt, gen, request_id=request_id)
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
