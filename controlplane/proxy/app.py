"""FastAPI application for the OpenAI-compatible ControlPlane proxy."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from controlplane.proxy.backend import HttpxOpenAIBackend, ModelBackend, build_backend
from controlplane.proxy.config import ProxySettings
from controlplane.proxy.streaming import iter_with_abort


class ProxyState:
    """Mutable application state kept separate from FastAPI route functions for testability."""

    def __init__(self, settings: ProxySettings, backend: ModelBackend) -> None:
        self.settings = settings
        self.backend = backend


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        yield
    finally:
        backend = getattr(app.state, "controlplane", None)
        if isinstance(backend, ProxyState) and isinstance(backend.backend, HttpxOpenAIBackend):
            await backend.backend.aclose()


def _incoming_headers(authorization: str | None) -> dict[str, str]:
    return {"authorization": authorization} if authorization else {}


def create_app(settings: ProxySettings | None = None, backend: ModelBackend | None = None) -> FastAPI:
    """Create a ControlPlane proxy app.

    ``settings`` and ``backend`` are injectable so tests can use the deterministic mock backend and
    future integration tests can plug in a fake model without opening a network connection.
    """
    settings = settings or ProxySettings.from_env()
    backend = backend or build_backend(settings)

    app = FastAPI(
        title="ControlPlane Proxy",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.controlplane = ProxyState(settings, backend)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "controlplane-proxy",
            "backend": settings.backend,
        }

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        model = "controlplane-mock" if settings.backend == "mock" else settings.upstream_base_url
        return {
            "object": "list",
            "data": [{"id": model, "object": "model", "owned_by": "controlplane"}],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        authorization: str | None = Header(default=None),
    ):
        try:
            payload = await request.json()
        except Exception as exc:  # pragma: no cover - FastAPI normally catches malformed JSON first.
            raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

        if not isinstance(payload, Mapping):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=422, detail="'messages' must be a non-empty list")

        stream = bool(payload.get("stream", False))
        incoming = _incoming_headers(authorization)

        try:
            if stream:
                source = backend.stream(payload, incoming)
                return StreamingResponse(
                    iter_with_abort(source),
                    media_type="text/event-stream",
                    headers={
                        "cache-control": "no-cache",
                        "connection": "keep-alive",
                    },
                )

            response = await backend.complete(payload, incoming)
            return JSONResponse(content=response)
        except Exception as exc:
            # Keep upstream details out of the public response while retaining the original exception for logs.
            raise HTTPException(status_code=502, detail=f"Model backend request failed: {exc}") from exc

    return app


app = create_app()
