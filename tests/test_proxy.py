from __future__ import annotations

import json

from fastapi.testclient import TestClient

from controlplane.proxy.app import create_app
from controlplane.proxy.config import ProxySettings


def _client() -> TestClient:
    settings = ProxySettings(backend="mock")
    return TestClient(create_app(settings=settings))


def test_health_and_models() -> None:
    with _client() as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["backend"] == "mock"

        models = client.get("/v1/models")
        assert models.status_code == 200
        assert models.json()["object"] == "list"
        assert models.json()["data"][0]["id"] == "controlplane-mock"


def test_chat_completion_non_streaming_is_openai_shaped() -> None:
    payload = {
        "model": "controlplane-mock",
        "messages": [{"role": "user", "content": "What are your support hours?"}],
    }
    with _client() as client:
        response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] >= 1


def test_chat_completion_streaming_returns_sse() -> None:
    payload = {
        "model": "controlplane-mock",
        "messages": [{"role": "user", "content": "Say hello"}],
        "stream": True,
    }
    with _client() as client:
        response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert lines
    assert lines[-1] == "data: [DONE]"
    first_payload = json.loads(lines[0][len("data: "):])
    assert first_payload["object"] == "chat.completion.chunk"


def test_messages_are_required() -> None:
    with _client() as client:
        response = client.post("/v1/chat/completions", json={"model": "controlplane-mock"})
    assert response.status_code == 422
