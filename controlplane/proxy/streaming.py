"""Streaming primitives for the ControlPlane proxy.

The first version is a pass-through wrapper with an optional chunk callback. P2 can later plug P1's
mid-stream risk predicate into the same seam without rewriting the HTTP endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

ChunkHook = Callable[[bytes], Awaitable[bool] | bool]


async def iter_with_abort(source: AsyncIterator[bytes], hook: ChunkHook | None = None) -> AsyncIterator[bytes]:
    """Forward chunks until the optional hook asks the stream to abort.

    The hook returns ``True`` to continue and ``False`` to stop. A later implementation can have the
    hook inspect reconstructed text, detector output, token counts, or remaining latency budget.
    """
    async for chunk in source:
        if hook is None:
            yield chunk
            continue

        decision = hook(chunk)
        if hasattr(decision, "__await__"):
            decision = await decision
        if not decision:
            return
        yield chunk
