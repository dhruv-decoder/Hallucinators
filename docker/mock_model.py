"""Tiny OpenAI-compatible mock model used by docker-compose and local smoke tests."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="ControlPlane Mock Model")


def _content(payload: dict[str, Any]) -> str:
    messages = payload.get("messages") or []
    prompt = ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            prompt = str(message.get("content", ""))
            break
    return f"Mock upstream response for: {prompt}"


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat(payload: dict[str, Any]):
    rid = f"chatcmpl-mock-{uuid.uuid4().hex[:12]}"
    content = _content(payload)
    if payload.get("stream"):
        async def stream():
            for token in content.split():
                chunk = {"id": rid, "object": "chat.completion.chunk", "created": int(time.time()),
                         "model": payload.get("model", "mock"), "choices": [{"index": 0, "delta": {"content": token + " "}, "finish_reason": None}]}
                yield f"data: {__import__('json').dumps(chunk)}\n\n"
            import json
            final = {"id": rid, "object": "chat.completion.chunk", "created": int(time.time()), "model": payload.get("model", "mock"), "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(final)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")
    return {
        "id": rid,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", "mock"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": max(1, len(str(payload.get("messages", "")).split())), "completion_tokens": len(content.split()), "total_tokens": len(content.split())},
    }
