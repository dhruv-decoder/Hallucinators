"""Model backend implementations used by the ControlPlane gateway.

The public contract is deliberately small. P2 controls transport; P1 can later attach the cascade
around the backend without coupling detector code to FastAPI or HTTP details.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol

import httpx

from controlplane.proxy.config import ProxySettings


class ModelBackend(Protocol):
    """Minimal backend protocol consumed by the proxy."""

    async def complete(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Return one OpenAI-compatible completion response."""

    async def stream(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> AsyncIterator[bytes]:
        """Yield OpenAI-compatible SSE bytes for a streaming completion."""


class MockBackend:
    """Deterministic local backend for demos and tests.

    It requires no API key or model download and makes the gateway independently runnable before a
    real provider is connected. The response is intentionally simple; P1/P3 can replace the text
    with richer demo scenarios later without changing proxy transport code.
    """

    model_name = "controlplane-mock"

    @staticmethod
    def _extract_prompt(payload: Mapping[str, Any]) -> str:
        messages = payload.get("messages") or []
        if not isinstance(messages, list):
            return ""
        for message in reversed(messages):
            if isinstance(message, Mapping) and message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

    @classmethod
    def _response(cls, payload: Mapping[str, Any], content: str) -> dict[str, Any]:
        model = str(payload.get("model") or cls.model_name)
        completion_id = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
        prompt = cls._extract_prompt(payload)
        prompt_tokens = max(1, len(prompt.split()))
        completion_tokens = max(1, len(content.split()))
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    @classmethod
    def _content(cls, payload: Mapping[str, Any]) -> str:
        prompt = cls._extract_prompt(payload)
        if not prompt:
            return "Mock response from ControlPlane."
        return f"Mock response from ControlPlane for: {prompt}"

    async def complete(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return self._response(payload, self._content(payload))

    async def stream(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> AsyncIterator[bytes]:
        response = self._response(payload, self._content(payload))
        completion_id = response["id"]
        created = response["created"]
        model = response["model"]
        content = response["choices"][0]["message"]["content"]

        # Chunk at whitespace boundaries to mimic a simple token stream.
        words = content.split()
        for index, word in enumerate(words):
            delta = {"role": "assistant"} if index == 0 else {}
            delta["content"] = word + (" " if index < len(words) - 1 else "")
            chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n".encode("utf-8")

        final_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk, separators=(',', ':'))}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"


class HttpxOpenAIBackend:
    """Proxy an OpenAI-compatible upstream using ``httpx``.

    LiteLLM can be introduced later as a provider abstraction, but this direct HTTP backend keeps
    the first gateway slice dependency-light and works with any upstream that exposes the standard
    ``/chat/completions`` contract.
    """

    def __init__(self, settings: ProxySettings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(timeout=settings.request_timeout_s)

    def _headers(self, incoming: Mapping[str, str]) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
        }
        if self.settings.api_key:
            headers["authorization"] = f"Bearer {self.settings.api_key}"
        elif incoming.get("authorization"):
            headers["authorization"] = incoming["authorization"]
        return headers

    @property
    def url(self) -> str:
        return f"{self.settings.upstream_base_url}/chat/completions"

    async def complete(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        response = await self._client.post(self.url, json=dict(payload), headers=self._headers(headers))
        response.raise_for_status()
        return response.json()

    async def stream(self, payload: Mapping[str, Any], headers: Mapping[str, str]) -> AsyncIterator[bytes]:
        async with self._client.stream(
            "POST",
            self.url,
            json=dict(payload),
            headers=self._headers(headers),
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()


def build_backend(settings: ProxySettings) -> ModelBackend:
    """Construct the configured backend, failing fast for unknown backend names."""
    if settings.backend == "mock":
        return MockBackend()
    if settings.backend in {"openai", "upstream", "http"}:
        return HttpxOpenAIBackend(settings)
    raise ValueError(f"Unsupported CONTROLPLANE_BACKEND={settings.backend!r}; use 'mock' or 'upstream'.")
