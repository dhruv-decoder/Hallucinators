"""The oversight service -- the single object The Tower's endpoints call.

It owns the long-lived pieces (the cascade engine, the P&L ledger, the flight recorder, the adaptive
thermostat, and the active policy profiles) and exposes one method, :meth:`oversee`, that takes a candidate
generation and runs the full inline pipeline:

    generation -> RequestContext -> thermostat scrutiny -> CascadeEngine.run -> PnlLedger.book
               -> apply_action (repair/redact/block) -> recorder.record -> notify UI subscribers

Everything downstream of the engine (the P&L, the receipt, the SSE fan-out) is done here so the HTTP layer
in ``app.py`` stays thin. Concurrency-safety: ``oversee`` holds a lock for the mutating section (ledger
totals, recorder hash chain, thermostat window, subscriber list) so parallel requests can't interleave and
corrupt the chain -- the detectors themselves are pure and run outside the lock.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

from controlplane.cascade.detectors import (
    GroundednessHeuristicDetector,
    ModelOverkillDetector,
    OverconfidenceDetector,
    RegexPiiDetector,
    SelfConsistencyDetector,
    SemanticCacheDetector,
)
from controlplane.cascade.engine import CascadeEngine
from controlplane.cascade.thermostat import Thermostat, risk_score
from controlplane.core.types import (
    Axis,
    PolicyProfile,
    RequestContext,
    VoIReceipt,
)
from controlplane.pnl import PnlLedger
from controlplane.proxy.actions import AppliedAction, apply_action
from controlplane.proxy.upstream import Generation
from controlplane.recorder import JsonlRecorder


def default_policies() -> dict[str, PolicyProfile]:
    """Two use-case profiles with different risk appetites (brief A1: different tolerances per use case).

    - ``support_bot`` -- customer-facing, balanced: a wrong refund policy is costly, so it verifies
      performance actively, but it also values low latency.
    - ``internal_copilot`` -- internal engineering assistant: higher tolerance for uncertainty (an engineer
      can sanity-check), lower stakes on a hallucination, so it escalates less and passes more.
    """
    return {
        "support_bot": PolicyProfile(
            id="support_bot@IN@balanced",
            cost_fail={Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0},
            cost_mitigate={Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10},
            block_threshold=0.85,
            escalate_threshold=0.5,
            annotate_threshold=0.2,
        ),
        "internal_copilot": PolicyProfile(
            id="internal_copilot@IN@lenient",
            cost_fail={Axis.PERFORMANCE: 0.4, Axis.RESPONSIBILITY: 4.0},
            cost_mitigate={Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10},
            block_threshold=0.9,
            escalate_threshold=0.65,
            annotate_threshold=0.35,
        ),
    }


@dataclass
class OverseeResult:
    """Everything an endpoint needs after oversight: the final text, the receipt, and the applied action."""

    final_text: str
    receipt: VoIReceipt
    applied: AppliedAction
    added_latency_ms: float
    scrutiny: float
    generation: Generation


@dataclass
class _Subscribers:
    """Thread-safe set of live SSE queues for the UI's receipt stream."""

    _qs: list[queue.Queue[VoIReceipt]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self) -> queue.Queue[VoIReceipt]:
        q: queue.Queue[VoIReceipt] = queue.Queue(maxsize=256)
        with self._lock:
            self._qs.append(q)
        return q

    def remove(self, q: queue.Queue[VoIReceipt]) -> None:
        with self._lock:
            if q in self._qs:
                self._qs.remove(q)

    def publish(self, receipt: VoIReceipt) -> None:
        with self._lock:
            targets = list(self._qs)
        for q in targets:
            try:
                q.put_nowait(receipt)
            except queue.Full:
                pass  # a slow UI client drops frames rather than blocking the request path


class OversightService:
    """Long-lived oversight state and the one entry point the proxy endpoints use."""

    def __init__(
        self,
        recorder_path: str | None = "recorder_log.jsonl",
        use_thermostat: bool = True,
    ) -> None:
        # The cache detector is stateful (it remembers seen prompts), so one shared instance.
        self.engine = CascadeEngine(
            detectors=[
                OverconfidenceDetector(),
                GroundednessHeuristicDetector(),
                SelfConsistencyDetector(),
                RegexPiiDetector(),
            ],
            cost_detectors=[ModelOverkillDetector(), SemanticCacheDetector()],
        )
        self.ledger = PnlLedger()
        self.recorder = JsonlRecorder(path=recorder_path)
        self.policies = default_policies()
        self.active_policy_key = "support_bot"
        self.thermostat = Thermostat() if use_thermostat else None
        self._subscribers = _Subscribers()
        self._lock = threading.Lock()
        self._request_seq = 0

    # -- policy --------------------------------------------------------------------------------------
    @property
    def policy(self) -> PolicyProfile:
        return self.policies[self.active_policy_key]

    def set_policy(self, key: str) -> None:
        if key not in self.policies:
            raise KeyError(key)
        self.active_policy_key = key

    def policy_for(self, use_case: str | None) -> tuple[str, PolicyProfile]:
        """Pick the policy for a request: its declared use case if we have a profile, else the active one."""
        if use_case and use_case in self.policies:
            return use_case, self.policies[use_case]
        return self.active_policy_key, self.policy

    # -- the pipeline --------------------------------------------------------------------------------
    def oversee(self, prompt: str, generation: Generation) -> OverseeResult:
        """Run the full inline oversight pipeline for one candidate generation."""
        import time

        policy_key, policy = self.policy_for(generation.use_case)
        ctx = RequestContext(
            request_id=self._next_request_id(),
            use_case=generation.use_case,
            prompt=prompt,
            response=generation.text,
            retrieved_context=generation.retrieved_context,
            samples=generation.samples,
            model=generation.model,
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
            meta={"injected_failure": generation.injected_failure} if generation.injected_failure else {},
        )

        # Detectors are pure -> run the (potentially slow) cascade outside the lock. Scrutiny is read from
        # the thermostat's current state; the feedback write happens under the lock below.
        scrutiny = self.thermostat.recommend() if self.thermostat else 1.0
        start = time.perf_counter()
        result = self.engine.run(ctx, scrutiny=scrutiny)
        applied = apply_action(generation.text, result, policy, generation.retrieved_context)
        added_latency_ms = (time.perf_counter() - start) * 1000.0

        # Mutating section: ledger totals, recorder hash chain, thermostat window, subscriber fan-out.
        with self._lock:
            pnl = self.ledger.book(ctx, result)
            receipt = self.recorder.record(
                result,
                pnl,
                policy_id=policy.id,
                repaired_output=applied.text if applied.modified else None,
            )
            if self.thermostat:
                self.thermostat.observe(risk_score(result))
            self._subscribers.publish(receipt)

        return OverseeResult(
            final_text=applied.text,
            receipt=receipt,
            applied=applied,
            added_latency_ms=added_latency_ms,
            scrutiny=scrutiny,
            generation=generation,
        )

    def _next_request_id(self) -> str:
        with self._lock:
            self._request_seq += 1
            return f"req-{self._request_seq:05d}"

    # -- UI feeds ------------------------------------------------------------------------------------
    def subscribe(self) -> queue.Queue[VoIReceipt]:
        return self._subscribers.add()

    def unsubscribe(self, q: queue.Queue[VoIReceipt]) -> None:
        self._subscribers.remove(q)

    def summary(self) -> dict:
        """Aggregate state for the dashboard header + P&L card."""
        totals = self.ledger.totals()
        receipts = self.recorder.receipts
        by_action: dict[str, int] = {}
        for r in receipts:
            by_action[r.action.value] = by_action.get(r.action.value, 0) + 1
        cleared_at_t0 = sum(1 for r in receipts if not any(s.ran and int(s.tier) > 0 for s in r.trace))
        n = len(receipts)
        return {
            "requests": n,
            "cost_saved_usd": round(totals.cost_saved_usd, 6),
            "safety_spend_usd": round(totals.safety_spend_usd, 6),
            "net_usd": round(totals.net_usd, 6),
            "self_funding": totals.net_usd < 0,
            "by_action": by_action,
            "cleared_at_t0_pct": round(100.0 * cleared_at_t0 / n, 1) if n else 100.0,
            "scrutiny": round(self.thermostat.scrutiny, 3) if self.thermostat else 1.0,
            "chain_valid": self.recorder.verify_chain(),
            "active_policy": self.policy.id,
            "policies": {k: v.id for k, v in self.policies.items()},
        }
