"""The tiered VoI cascade engine.

For one request the engine:

1. Runs every cost-axis detector (all T0, effectively free) to collect savings opportunities.
2. For each failure-type axis (performance, responsibility):
   a. Runs all free T0 detectors and calibrates their scores into probabilities.
   b. Combines them into a single axis failure probability ``p``.
   c. For each higher-tier (T1, then T2) detector, applies the VoI stopping rule: run it only if the
      value of its information exceeds its dollar + latency cost. If it runs, recalibrate and recombine.
   d. Records a ``VoIStep`` for every detector it considered -- ran or skipped -- so the receipt shows
      exactly why the cascade stopped where it did.
3. Chooses an action from the final per-axis probabilities and the policy.

The tier loop is sequential by design: whether to climb depends on what the cheaper tiers already found.
Detectors *within* a tier are independent and can be run in parallel; that concurrency is a latency
optimisation owned by the proxy layer (P2) and does not change the decision logic here.
"""

from __future__ import annotations

from controlplane.cascade import voi
from controlplane.cascade.calibration import Calibrator, IdentityCalibrator
from controlplane.cascade.decision import decide_action
from controlplane.cascade.detectors.base import CostDetector, Detector
from controlplane.core.types import (
    Action,
    Axis,
    AxisOutcome,
    CascadeResult,
    PolicyProfile,
    RequestContext,
    Signal,
    Tier,
    VoIStep,
)

# Failure-type axes go through the VoI machinery. The cost axis is handled separately (it is the funding
# side, not a failure probability).
_FAILURE_AXES = (Axis.PERFORMANCE, Axis.RESPONSIBILITY)


class CascadeEngine:
    """Runs the VoI cascade for a single request and returns a ``CascadeResult``."""

    def __init__(
        self,
        detectors: list[Detector],
        cost_detectors: list[CostDetector] | None = None,
        policy: PolicyProfile | None = None,
        calibrators: dict[str, Calibrator] | None = None,
        combine_strategy: str = "noisy_or",
    ) -> None:
        self.detectors = sorted(detectors, key=lambda d: int(d.tier))
        self.cost_detectors = cost_detectors or []
        self.policy = policy or PolicyProfile()
        self.calibrators = calibrators or {}
        self.combine_strategy = combine_strategy

    def _calibrate(self, signal: Signal) -> float:
        """Map a detector's raw score to a calibrated probability using its calibrator (identity default)."""
        calibrator = self.calibrators.get(signal.name, IdentityCalibrator())
        return calibrator.predict_one(signal.score)

    def run(self, ctx: RequestContext) -> CascadeResult:
        result = CascadeResult(request_id=ctx.request_id, use_case=ctx.use_case)

        # 1. Cost axis: run every (free) cost detector.
        for cost_detector in self.cost_detectors:
            result.cost_opportunities.append(cost_detector.run(ctx))

        # 2. Failure-type axes: VoI cascade per axis.
        loss_before = 0.0
        loss_after = 0.0
        for axis in _FAILURE_AXES:
            axis_detectors = [d for d in self.detectors if d.axis == axis]
            if not axis_detectors:
                continue
            outcome, p_after_t0 = self._run_axis(ctx, axis, axis_detectors, result)
            result.per_axis[axis] = outcome
            cost_fail = self.policy.cost_fail.get(axis, 1.0)
            loss_before += p_after_t0 * cost_fail
            loss_after += outcome.p_fail * cost_fail

        result.expected_loss_before = loss_before
        result.expected_loss_after = loss_after

        # 3. Decide the action.
        action, reason = decide_action(result.per_axis, self.policy)
        result.action = action
        result.stopping_reason = _summarize_stop(result, action, reason)
        return result

    def _run_axis(
        self,
        ctx: RequestContext,
        axis: Axis,
        axis_detectors: list[Detector],
        result: CascadeResult,
    ) -> tuple[AxisOutcome, float]:
        """Run one axis's cascade. Returns its outcome and the probability after only the T0 tier."""
        cost_fail = self.policy.cost_fail.get(axis, 1.0)
        cost_mitigate = self.policy.cost_mitigate.get(axis, 0.05)

        axis_signals: list[Signal] = []
        probs: list[float] = []
        p_after_t0 = 0.0

        for detector in axis_detectors:
            if not detector.applicable(ctx):
                # Nothing to work with (e.g. groundedness without context). Skip without paying.
                p_now = voi.combine_probabilities(probs, self.combine_strategy)
                result.trace.append(
                    VoIStep(
                        axis=axis,
                        detector=detector.name,
                        tier=detector.tier,
                        p_fail_before=p_now,
                        p_fail_after=None,
                        voi=0.0,
                        check_cost=0.0,
                        ran=False,
                        reason="not_applicable",
                    )
                )
                continue

            if detector.tier == Tier.T0:
                # T0 is effectively free -> always run it.
                signal = detector.run(ctx)
                signal.p_fail = self._calibrate(signal)
                axis_signals.append(signal)
                result.signals.append(signal)
                probs.append(signal.p_fail)
                p_current = voi.combine_probabilities(probs, self.combine_strategy)
                result.trace.append(
                    VoIStep(
                        axis=axis,
                        detector=detector.name,
                        tier=detector.tier,
                        p_fail_before=p_current,
                        p_fail_after=p_current,
                        voi=0.0,
                        check_cost=0.0,
                        ran=True,
                        reason="tier0_always_on",
                    )
                )
                p_after_t0 = p_current
                continue

            # Higher tiers: apply the stopping rule.
            p_before = voi.combine_probabilities(probs, self.combine_strategy)
            decision = voi.decide_check(
                p_fail=p_before,
                cost_fail=cost_fail,
                cost_mitigate=cost_mitigate,
                informativeness=detector.informativeness,
                detector_cost_usd=detector.est_cost_usd,
                detector_latency_ms=detector.est_latency_ms,
                lambda_latency=self.policy.lambda_latency,
            )
            if not decision.run:
                result.trace.append(
                    VoIStep(
                        axis=axis,
                        detector=detector.name,
                        tier=detector.tier,
                        p_fail_before=p_before,
                        p_fail_after=None,
                        voi=decision.voi,
                        check_cost=decision.cost,
                        ran=False,
                        reason=decision.reason,
                    )
                )
                continue

            signal = detector.run(ctx)
            signal.p_fail = self._calibrate(signal)
            axis_signals.append(signal)
            result.signals.append(signal)
            probs.append(signal.p_fail)
            p_after = voi.combine_probabilities(probs, self.combine_strategy)
            result.trace.append(
                VoIStep(
                    axis=axis,
                    detector=detector.name,
                    tier=detector.tier,
                    p_fail_before=p_before,
                    p_fail_after=p_after,
                    voi=decision.voi,
                    check_cost=decision.cost,
                    ran=True,
                    reason=decision.reason,
                )
            )

        p_final = voi.combine_probabilities(probs, self.combine_strategy)
        outcome = AxisOutcome(
            axis=axis,
            p_fail=p_final,
            expected_loss=voi.expected_loss(p_final, cost_fail),
            signals=axis_signals,
        )
        return outcome, p_after_t0


def _summarize_stop(result: CascadeResult, action: Action, decision_reason: str) -> str:
    """Build a one-line human-readable summary of why the cascade stopped and acted as it did."""
    ran = sum(1 for step in result.trace if step.ran)
    skipped = sum(1 for step in result.trace if not step.ran)
    return f"action={action.value} ({decision_reason}); checks_run={ran}, checks_skipped={skipped}"
