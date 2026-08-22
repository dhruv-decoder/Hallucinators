"""Minimal OpenAI-compatible request/response schemas.

Just enough of the Chat Completions surface for a standard OpenAI client to talk to The Tower unchanged:
the fields real callers send, plus a ``controlplane`` extension block we add to every response so a caller
(or the UI) can read what oversight did without a second request.

We deliberately do not re-implement the whole OpenAI schema -- only the fields the proxy reads or returns.
Unknown fields are ignored, so a caller passing ``temperature``/``top_p``/etc. still works.
"""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field

from controlplane.core.types import Action, Axis


class ChatMessage(BaseModel):
    """One message in the OpenAI chat format."""

    role: str
    content: str = ""


class ChatCompletionRequest(BaseModel):
    """The subset of the OpenAI Chat Completions request The Tower reads.

    ``retrieved_context`` and ``samples`` are ControlPlane extensions: a RAG application can pass the source
    chunks it grounded on and any extra self-consistency samples so the groundedness / self-consistency
    detectors have real material. Standard OpenAI callers omit them and the simulated upstream supplies its
    own, so the demo works either way.
    """

    model: str = "controlplane-sim"
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    # ControlPlane extensions (ignored by a vanilla OpenAI server; honoured here).
    retrieved_context: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)
    use_case: str | None = None

    model_config = {"extra": "ignore"}

    def last_user_prompt(self) -> str:
        """The most recent user message -- what the model is actually answering."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return self.messages[-1].content if self.messages else ""


class OversightBlock(BaseModel):
    """The ControlPlane extension attached to every completion: what oversight decided and why.

    This is the receipt in miniature -- enough for a caller to act on (was it repaired? blocked?) and a
    pointer (``receipt_id``) to the full hash-chained receipt in the flight recorder.
    """

    action: Action
    receipt_id: str
    per_axis_p_fail: dict[Axis, float] = Field(default_factory=dict)
    modified: bool = False
    stopping_reason: str = ""
    net_usd: float = 0.0
    added_latency_ms: float = 0.0
    policy_id: str = ""


def chat_completion_response(
    text: str,
    model: str,
    oversight: OversightBlock,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> dict:
    """Assemble an OpenAI-shaped ``chat.completion`` object plus the ``controlplane`` block."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "controlplane": oversight.model_dump(mode="json"),
    }


def chat_completion_chunk(
    delta_content: str | None,
    model: str,
    finish_reason: str | None = None,
    oversight: OversightBlock | None = None,
    chunk_id: str | None = None,
) -> dict:
    """Assemble one OpenAI-shaped ``chat.completion.chunk`` for the streaming path."""
    delta: dict = {}
    if delta_content is not None:
        delta["content"] = delta_content
    obj: dict = {
        "id": chunk_id or f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if oversight is not None:
        obj["controlplane"] = oversight.model_dump(mode="json")
    return obj
