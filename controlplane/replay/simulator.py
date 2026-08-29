"""The What-If / Replay simulator: the proof engine for "safer AND cheaper".

It re-runs the same fixed workload under different oversight policies (and against an "oversight off"
baseline) and reports, for each, two things a skeptic cares about:

- **residual risk** -- the model-estimated expected loss of the answers that still reach users. An answer
  that is blocked, escalated, or repaired is treated as handled (its risk is removed); an answer that is
  passed or annotated still carries its expected loss. Lower is safer.
- **net cost** -- safety spend minus cost saved. Negative means oversight paid for itself.

"Oversight off" is the honest baseline: every answer reaches the user unchanged and nothing is routed
down or cached, so residual risk equals the full estimated risk and net cost is zero savings. The gap
between it and a ControlPlane policy is exactly what the layer buys.

Important honesty note: the risk numbers are estimated by ControlPlane's own detectors, not measured
against ground truth. They are a consistent internal comparison across policies, not a claim of measured
failure rates -- those come from the labelled eval harness. To keep scenarios comparable, vary the risk
*appetite* (the action thresholds) while holding the risk model (``cost_fail``) constant, so ``total_risk``
is identical across scenarios and only ``residual_risk`` moves.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Action, PolicyProfile, RequestContext
from controlplane.pnl import PnlLedger

# Actions after which the answer still reaches the user, so it keeps carrying its estimated risk.
_RISK_REACHES_USER = {Action.PASS, Action.ANNOTATE}

EngineFactory = Callable[[PolicyProfile], CascadeEngine]


class ScenarioResult(BaseModel):
    """Aggregate outcome of running the workload under one scenario."""

    name: str
    n_requests: int
    action_counts: dict[str, int] = Field(default_factory=dict)
    total_risk: float = 0.0  # estimated expected loss if every answer reached the user
    residual_risk: float = 0.0  # estimated expected loss of answers that still reach the user
    cost_saved_usd: float = 0.0
    safety_spend_usd: float = 0.0
    human_review_usd: float = 0.0  # analyst time booked for the escalations this appetite triggers
    added_latency_ms: float = 0.0

    @property
    def risk_reduction(self) -> float:
        return self.total_risk - self.residual_risk

    @property
    def risk_reduction_pct(self) -> float:
        return 100.0 * self.risk_reduction / self.total_risk if self.total_risk > 0 else 0.0

    @property
    def net_usd(self) -> float:
        """Automated net: safety-check spend minus cost-axis savings. Negative means the automated
        oversight paid for itself (the self-funding claim). Human review is excluded here on purpose."""
        return self.safety_spend_usd - self.cost_saved_usd

    @property
    def total_cost_usd(self) -> float:
        """All-in cost of running this appetite: automated net plus the human-review time it triggers.
        This is the number that moves with risk appetite -- stricter escalates more and costs more."""
        return self.net_usd + self.human_review_usd

    @property
    def escalation_rate(self) -> float:
        n = self.n_requests
        return self.action_counts.get(Action.ESCALATE.value, 0) / n if n else 0.0


class WhatIfSimulator:
    """Re-runs a fixed workload under different policies. Each run gets a fresh engine and ledger so
    stateful detectors (e.g. the semantic cache) and P&L totals do not leak between scenarios."""

    def __init__(self, requests: list[RequestContext], engine_factory: EngineFactory) -> None:
        self.requests = requests
        self.engine_factory = engine_factory

    def run_scenario(
        self, name: str, policy: PolicyProfile, apply_controls: bool = True
    ) -> ScenarioResult:
        """Run the workload once. ``apply_controls=False`` models oversight being off entirely."""
        engine = self.engine_factory(policy)
        ledger = PnlLedger()
        action_counts: dict[str, int] = {}
        total_risk = 0.0
        residual_risk = 0.0
        added_latency = 0.0

        for ctx in self.requests:
            result = engine.run(ctx)
            ledger.book(ctx, result)
            total_risk += result.expected_loss_after
            added_latency += sum(sig.latency_ms for sig in result.signals)

            if apply_controls:
                action_counts[result.action.value] = action_counts.get(result.action.value, 0) + 1
                if result.action in _RISK_REACHES_USER:
                    residual_risk += result.expected_loss_after
            else:
                # Oversight off: every answer is forwarded as-is; nothing is routed down or cached.
                action_counts[Action.PASS.value] = action_counts.get(Action.PASS.value, 0) + 1
                residual_risk += result.expected_loss_after

        totals = ledger.totals()
        escalations = action_counts.get(Action.ESCALATE.value, 0) if apply_controls else 0
        return ScenarioResult(
            name=name,
            n_requests=len(self.requests),
            action_counts=action_counts,
            total_risk=total_risk,
            residual_risk=residual_risk,
            cost_saved_usd=totals.cost_saved_usd if apply_controls else 0.0,
            safety_spend_usd=totals.safety_spend_usd if apply_controls else 0.0,
            human_review_usd=ledger.pricing.review_cost(escalations),
            added_latency_ms=added_latency if apply_controls else 0.0,
        )

    def compare(self, policies: dict[str, PolicyProfile]) -> dict[str, ScenarioResult]:
        """Run an 'oversight off' baseline plus one scenario per named policy."""
        results: dict[str, ScenarioResult] = {}
        baseline_policy = next(iter(policies.values())) if policies else PolicyProfile()
        results["oversight_off"] = self.run_scenario(
            "oversight_off", baseline_policy, apply_controls=False
        )
        for name, policy in policies.items():
            results[name] = self.run_scenario(name, policy, apply_controls=True)
        return results
