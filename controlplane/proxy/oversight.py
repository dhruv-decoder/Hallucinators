"""Small integration service that connects the gateway to P1's cascade and P2's recorder/policy.

The gateway owns transport concerns; this service owns the P2 orchestration seam.  The actual detectors,
VoI math and action decision remain in the existing P1 modules.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from controlplane.cascade.detectors.cost import ModelOverkillDetector, SemanticCacheDetector
from controlplane.cascade.detectors.performance import (
    GroundednessHeuristicDetector,
    OverconfidenceDetector,
    SelfConsistencyDetector,
)
from controlplane.cascade.detectors.responsibility import RegexPiiDetector
from controlplane.cascade.async_engine import AsyncCascadeRunner
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Action, PolicyProfile, RequestContext, VoIReceipt
from controlplane.pnl import PnlLedger
from controlplane.policy import PolicyManager
from controlplane.recorder import SQLiteFlightRecorder


class OversightService:
    """Run the existing cascade under the active policy and persist its VoI receipt."""

    def __init__(self, policy_manager: PolicyManager, recorder: SQLiteFlightRecorder) -> None:
        self.policy_manager = policy_manager
        self.recorder = recorder
        self.ledger = PnlLedger()
        self._detectors = [
            OverconfidenceDetector(),
            GroundednessHeuristicDetector(),
            SelfConsistencyDetector(),
            RegexPiiDetector(),
        ]
        self._cost_detectors = [ModelOverkillDetector(), SemanticCacheDetector()]

    def _engine(self, policy: PolicyProfile) -> CascadeEngine:
        return CascadeEngine(
            detectors=self._detectors,
            cost_detectors=self._cost_detectors,
            policy=policy,
        )

    async def inspect_async(
        self,
        *,
        request_id: str,
        payload: Mapping[str, Any],
        response_text: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        use_case: str = "default",
        geography: str = "*",
        risk_appetite: str = "balanced",
        latency_budget_ms: float = 100.0,
        tier_timeout_ms: dict[int, float] | None = None,
        response_meta: Mapping[str, Any] | None = None,
    ) -> VoIReceipt:
        policy = self.policy_manager.resolve(use_case=use_case, geography=geography, risk_appetite=risk_appetite)
        ctx = self._build_context(
            request_id, payload, response_text, model, input_tokens, output_tokens,
            use_case, geography, risk_appetite, response_meta,
        )
        engine = self._engine(policy)
        runner = AsyncCascadeRunner(engine)
        from controlplane.core.types import Tier
        cfg = tier_timeout_ms or {}
        timeouts = {Tier.T0: cfg.get(0, 25.0), Tier.T1: cfg.get(1, 75.0), Tier.T2: cfg.get(2, 250.0)}
        result = await runner.run(ctx, latency_budget_ms=latency_budget_ms, tier_timeout_ms=timeouts)
        pnl = self.ledger.book(ctx, result)
        return self.recorder.record(result, pnl, policy_id=policy.id)

    def _build_context(
        self,
        request_id: str,
        payload: Mapping[str, Any],
        response_text: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        use_case: str,
        geography: str,
        risk_appetite: str,
        response_meta: Mapping[str, Any] | None = None,
    ) -> RequestContext:
        messages = payload.get("messages") or []
        prompt = ""
        for message in reversed(messages):
            if isinstance(message, Mapping) and message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    prompt = content
                    break
        context = payload.get("retrieved_context", [])
        samples = payload.get("samples", [])
        return RequestContext(
            request_id=request_id,
            use_case=use_case,
            prompt=prompt,
            response=response_text,
            retrieved_context=context if isinstance(context, list) else [],
            samples=samples if isinstance(samples, list) else [],
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            meta={
                "geography": geography,
                "risk_appetite": risk_appetite,
                **(dict(response_meta) if response_meta else {}),
            },
        )

    def should_abort_stream(self, text: str) -> bool:
        """Cheap fail-safe predicate; P1 can later inject the learned forecasting predicate here."""
        detector = RegexPiiDetector()
        ctx = RequestContext(request_id=str(uuid.uuid4()), response=text)
        return detector.run(ctx).score >= 1.0

    def inspect(
        self,
        *,
        request_id: str,
        payload: Mapping[str, Any],
        response_text: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        use_case: str = "default",
        geography: str = "*",
        risk_appetite: str = "balanced",
        response_meta: Mapping[str, Any] | None = None,
    ) -> VoIReceipt:
        policy = self.policy_manager.resolve(
            use_case=use_case,
            geography=geography,
            risk_appetite=risk_appetite,
        )
        messages = payload.get("messages") or []
        prompt = ""
        for message in reversed(messages):
            if isinstance(message, Mapping) and message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    prompt = content
                    break
        context = payload.get("retrieved_context", [])
        samples = payload.get("samples", [])
        ctx = RequestContext(
            request_id=request_id,
            use_case=use_case,
            prompt=prompt,
            response=response_text,
            retrieved_context=context if isinstance(context, list) else [],
            samples=samples if isinstance(samples, list) else [],
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            meta={
                "geography": geography,
                "risk_appetite": risk_appetite,
                **(dict(response_meta) if response_meta else {}),
            },
        )
        result = self._engine(policy).run(ctx)
        pnl = self.ledger.book(ctx, result)
        return self.recorder.record(result, pnl, policy_id=policy.id)

    @staticmethod
    def action_headers(receipt: VoIReceipt) -> dict[str, str]:
        return {
            "x-controlplane-request-id": receipt.request_id,
            "x-controlplane-action": receipt.action.value,
            "x-controlplane-policy": receipt.policy_id,
            "x-controlplane-receipt-hash": receipt.hash_self,
        }


def parse_stream_chunk(chunk: bytes) -> str:
    """Extract assistant text from one OpenAI-compatible SSE chunk, returning empty text when irrelevant."""
    text = chunk.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        try:
            payload = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content", "")
        if isinstance(content, str):
            return content
    return ""


async def monitored_stream(
    source: AsyncIterator[bytes],
    *,
    service: OversightService,
    request_id: str,
    payload: Mapping[str, Any],
    model: str,
    use_case: str,
    geography: str,
    risk_appetite: str,
    latency_budget_ms: float = 100.0,
    tier_timeout_ms: dict[int, float] | None = None,
    abort_predicate: Callable[[str], bool | Awaitable[bool]] | None = None,
) -> AsyncIterator[bytes]:
    """Forward a stream, optionally abort mid-stream, then persist an async oversight receipt."""
    pieces: list[str] = []
    aborted = False
    async for chunk in source:
        piece = parse_stream_chunk(chunk)
        if piece:
            pieces.append(piece)
        if abort_predicate is not None:
            decision = abort_predicate("".join(pieces))
            if hasattr(decision, "__await__"):
                decision = await decision
            if decision:
                aborted = True
                break
        yield chunk
    content = "".join(pieces)
    await service.inspect_async(
        request_id=request_id,
        payload=payload,
        response_text=content,
        model=model,
        input_tokens=_estimate_input_tokens(payload),
        output_tokens=max(1, len(content.split())) if content else 0,
        use_case=use_case,
        geography=geography,
        risk_appetite=risk_appetite,
        latency_budget_ms=latency_budget_ms,
        tier_timeout_ms=tier_timeout_ms,
        response_meta={"stream": True, "aborted": aborted},
    )
    if aborted:
        yield b"data: [DONE]\n\n"


def _estimate_input_tokens(payload: Mapping[str, Any]) -> int:
    messages = payload.get("messages") or []
    text_parts = [
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, Mapping)
    ]
    return max(1, len(" ".join(text_parts).split())) if text_parts else 0
