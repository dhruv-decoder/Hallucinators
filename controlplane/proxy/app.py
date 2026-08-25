"""FastAPI application for the OpenAI-compatible ControlPlane proxy."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from controlplane.core.types import Action
from controlplane.policy import PolicyManager
from controlplane.proxy.backend import HttpxOpenAIBackend, ModelBackend, build_backend
from controlplane.proxy.config import ProxySettings
from controlplane.proxy.oversight import OversightService, monitored_stream
from controlplane.proxy.streaming import iter_with_abort
from controlplane.recorder import SQLiteFlightRecorder


class ProxyState:
    """Mutable application state kept separate from FastAPI route functions for testability."""

    def __init__(self, settings: ProxySettings, backend: ModelBackend) -> None:
        self.settings = settings
        self.backend = backend
        self.recorder = SQLiteFlightRecorder(settings.recorder_db_path)
        self.policy_manager = PolicyManager(settings.policy_path)
        self.oversight = OversightService(self.policy_manager, self.recorder) if settings.oversight_enabled else None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        yield
    finally:
        state = getattr(app.state, "controlplane", None)
        if isinstance(state, ProxyState):
            state.recorder.close()
            if isinstance(state.backend, HttpxOpenAIBackend):
                await state.backend.aclose()


def _incoming_headers(authorization: str | None) -> dict[str, str]:
    return {"authorization": authorization} if authorization else {}


def _request_id(header: str | None) -> str:
    return header.strip() if header and header.strip() else str(uuid.uuid4())


def _oversight_context(
    state: ProxyState,
    *,
    use_case: str | None,
    geography: str | None,
    risk_appetite: str | None,
) -> tuple[str, str, str]:
    return (
        use_case or state.settings.default_use_case,
        geography or state.settings.default_geography,
        risk_appetite or state.settings.default_risk_appetite,
    )


def _apply_action_headers(receipt) -> dict[str, str]:
    return {
        "x-controlplane-request-id": receipt.request_id,
        "x-controlplane-action": receipt.action.value,
        "x-controlplane-policy": receipt.policy_id,
        "x-controlplane-receipt-hash": receipt.hash_self,
    }


def create_app(settings: ProxySettings | None = None, backend: ModelBackend | None = None) -> FastAPI:
    settings = settings or ProxySettings.from_env()
    backend = backend or build_backend(settings)
    app = FastAPI(title="ControlPlane Proxy", version="0.1.0", lifespan=_lifespan)
    app.state.controlplane = ProxyState(settings, backend)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        state: ProxyState = app.state.controlplane
        return {
            "status": "ok",
            "service": "controlplane-proxy",
            "backend": settings.backend,
            "oversight": settings.oversight_enabled,
            "recorder": "sqlite",
            "recorder_count": state.recorder.count(),
            "policy_profiles": len(state.policy_manager.profiles()),
            "latency_budget_ms": settings.latency_budget_ms,
            "stream_abort_enabled": settings.stream_abort_enabled,
        }

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        model = "controlplane-mock" if settings.backend == "mock" else settings.upstream_base_url
        return {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "controlplane"}]}

    @app.get("/v1/oversight/receipts")
    async def receipts(
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        use_case: str | None = None,
        policy_id: str | None = None,
    ) -> dict[str, Any]:
        state: ProxyState = app.state.controlplane
        receipts = state.recorder.list(
            limit=limit,
            offset=offset,
            action=action,
            use_case=use_case,
            policy_id=policy_id,
        )
        return {
            "object": "list",
            "data": [receipt.model_dump(mode="json") for receipt in receipts],
            "count": state.recorder.count(),
        }

    @app.get("/v1/oversight/receipts/{request_id}")
    async def receipt(request_id: str) -> dict[str, Any]:
        stored = app.state.controlplane.recorder.get(request_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Receipt not found")
        return stored.model_dump(mode="json")

    @app.get("/v1/oversight/verify")
    async def verify_chain() -> dict[str, Any]:
        recorder = app.state.controlplane.recorder
        return {"valid": recorder.verify_chain(), "count": recorder.count()}

    @app.get("/v1/policies")
    async def policies() -> dict[str, Any]:
        return app.state.controlplane.policy_manager.snapshot()

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        authorization: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_controlplane_use_case: str | None = Header(default=None),
        x_controlplane_geography: str | None = Header(default=None),
        x_controlplane_risk_appetite: str | None = Header(default=None),
    ):
        try:
            payload = await request.json()
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

        if not isinstance(payload, Mapping):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=422, detail="'messages' must be a non-empty list")

        state: ProxyState = app.state.controlplane
        request_id = _request_id(x_request_id)
        stream = bool(payload.get("stream", False))
        incoming = _incoming_headers(authorization)
        use_case, geography, risk_appetite = _oversight_context(
            state,
            use_case=x_controlplane_use_case,
            geography=x_controlplane_geography,
            risk_appetite=x_controlplane_risk_appetite,
        )

        try:
            if stream:
                source = backend.stream(payload, incoming)
                if state.oversight is not None:
                    source = monitored_stream(
                        source,
                        service=state.oversight,
                        request_id=request_id,
                        payload=payload,
                        model=str(payload.get("model") or ""),
                        use_case=use_case,
                        geography=geography,
                        risk_appetite=risk_appetite,
                        latency_budget_ms=settings.latency_budget_ms,
                        tier_timeout_ms={0: settings.tier_timeout_t0_ms, 1: settings.tier_timeout_t1_ms, 2: settings.tier_timeout_t2_ms},
                        abort_predicate=state.oversight.should_abort_stream if settings.stream_abort_enabled else None,
                    )
                return StreamingResponse(
                    iter_with_abort(source),
                    media_type="text/event-stream",
                    headers={"cache-control": "no-cache", "connection": "keep-alive", "x-controlplane-request-id": request_id},
                )

            response = await backend.complete(payload, incoming)
            headers = {"x-controlplane-request-id": request_id}
            if state.oversight is not None:
                choices = response.get("choices") or []
                content = ""
                if choices:
                    content = str((choices[0].get("message") or {}).get("content", ""))
                usage = response.get("usage") or {}
                receipt = await state.oversight.inspect_async(
                    request_id=request_id,
                    payload=payload,
                    response_text=content,
                    model=str(response.get("model") or payload.get("model") or ""),
                    input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage.get("completion_tokens", 0) or 0),
                    use_case=use_case,
                    geography=geography,
                    risk_appetite=risk_appetite,
                    latency_budget_ms=settings.latency_budget_ms,
                    tier_timeout_ms={0: settings.tier_timeout_t0_ms, 1: settings.tier_timeout_t1_ms, 2: settings.tier_timeout_t2_ms},
                )
                headers.update(_apply_action_headers(receipt))
                if receipt.action == Action.BLOCK:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": {
                                "message": "ControlPlane blocked this response under the active policy.",
                                "type": "controlplane_policy_violation",
                            }
                        },
                        headers=headers,
                    )
            return JSONResponse(content=response, headers=headers)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Model backend request failed: {exc}") from exc

    return app


app = create_app()
