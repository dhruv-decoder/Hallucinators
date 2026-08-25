"""Async detector execution for the ControlPlane cascade.

P2 owns this execution layer: tiers remain sequential because the VoI decision depends on the
previous tier, while independent detectors within a tier fan out concurrently. Deadlines are
measured as wall-clock budgets rather than as the sum of detector latencies.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable

from controlplane.cascade import voi
from controlplane.cascade.calibration import Calibrator, IdentityCalibrator
from controlplane.cascade.detectors.base import CostDetector, Detector
from controlplane.core.types import Axis, CascadeResult, PolicyProfile, RequestContext, Signal, Tier, VoIStep


async def run_detectors_parallel(
    detectors: Iterable[Detector],
    ctx: RequestContext,
    *,
    timeout_ms: float | None = None,
) -> tuple[list[tuple[Detector, Signal]], list[Detector], float]:
    """Run independent detectors concurrently.

    Returns completed ``(detector, signal)`` pairs, timed-out detectors, and wall-clock milliseconds.
    Detector ``run`` is synchronous today, so it is moved to worker threads to preserve concurrency.
    """
    detectors = list(detectors)
    if not detectors:
        return [], [], 0.0

    start = time.perf_counter()
    tasks = [asyncio.create_task(asyncio.to_thread(detector.run, ctx)) for detector in detectors]
    timeout = None if timeout_ms is None else max(timeout_ms, 0.0) / 1000.0
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    timed_out = [detectors[i] for i, task in enumerate(tasks) if task in pending]
    for task in pending:
        task.cancel()
    completed: list[tuple[Detector, Signal]] = []
    for i, task in enumerate(tasks):
        if task not in done:
            continue
        try:
            completed.append((detectors[i], task.result()))
        except Exception:
            # Individual detector failure should not crash the whole cascade; the caller records it as skipped.
            continue
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return completed, timed_out, elapsed_ms


class AsyncCascadeRunner:
    """Execute a ``CascadeEngine`` with parallel fan-out and explicit budgets."""

    def __init__(self, engine) -> None:
        self.engine = engine

    async def run(
        self,
        ctx: RequestContext,
        *,
        scrutiny: float = 1.0,
        latency_budget_ms: float = 100.0,
        tier_timeout_ms: dict[Tier, float] | None = None,
    ) -> CascadeResult:
        budget_ms = max(float(latency_budget_ms), 0.0)
        timeout_cfg = tier_timeout_ms or {Tier.T0: 25.0, Tier.T1: 75.0, Tier.T2: 250.0}
        result = CascadeResult(request_id=ctx.request_id, use_case=ctx.use_case)
        started = time.perf_counter()
        deadline = started + budget_ms / 1000.0

        # T0 cost detectors are independent and can be evaluated in parallel. They are synchronous
        # today, so offload them to threads.
        if self.engine.cost_detectors:
            tasks = [asyncio.create_task(asyncio.to_thread(detector.run, ctx)) for detector in self.engine.cost_detectors]
            remaining = max(deadline - time.perf_counter(), 0.0)
            done, pending = await asyncio.wait(tasks, timeout=remaining)
            for task in pending:
                task.cancel()
            for task in done:
                try:
                    result.cost_opportunities.append(task.result())
                except Exception:
                    continue

        loss_before = 0.0
        loss_after = 0.0
        for axis in (Axis.PERFORMANCE, Axis.RESPONSIBILITY):
            detectors = [d for d in self.engine.detectors if d.axis == axis]
            if not detectors:
                continue
            outcome, p_after_t0 = await self._run_axis(
                ctx,
                axis,
                detectors,
                result,
                scrutiny=scrutiny,
                deadline=deadline,
                timeout_cfg=timeout_cfg,
            )
            result.per_axis[axis] = outcome
            cost_fail = self.engine.policy.cost_fail.get(axis, 1.0)
            loss_before += p_after_t0 * cost_fail
            loss_after += outcome.p_fail * cost_fail

        result.expected_loss_before = loss_before
        result.expected_loss_after = loss_after
        from controlplane.cascade.decision import decide_action
        action, reason = decide_action(result.per_axis, self.engine.policy)
        result.action = action
        result.stopping_reason = (
            f"async action={action.value} ({reason}); "
            f"wall_latency_ms={(time.perf_counter() - started) * 1000.0:.2f}; budget_ms={budget_ms:.2f}"
        )
        return result

    async def _run_axis(
        self,
        ctx: RequestContext,
        axis: Axis,
        axis_detectors: list[Detector],
        result: CascadeResult,
        *,
        scrutiny: float,
        deadline: float,
        timeout_cfg: dict[Tier, float],
    ) -> tuple[any, float]:
        from controlplane.core.types import AxisOutcome

        cost_fail = self.engine.policy.cost_fail.get(axis, 1.0)
        cost_mitigate = self.engine.policy.cost_mitigate.get(axis, 0.05)
        ceiling = self.engine.policy.tier_ceilings.get(axis, Tier.T2)
        axis_signals: list[Signal] = []
        probs: list[float] = []
        p_after_t0 = 0.0

        by_tier: dict[Tier, list[Detector]] = {}
        for detector in axis_detectors:
            by_tier.setdefault(detector.tier, []).append(detector)

        for tier in sorted(by_tier, key=int):
            tier_detectors = by_tier[tier]
            applicable = [d for d in tier_detectors if d.applicable(ctx)]
            for d in tier_detectors:
                if d not in applicable:
                    p_now = voi.combine_probabilities(probs, self.engine.combine_strategy)
                    result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier, p_fail_before=p_now,
                                                p_fail_after=None, voi=0.0, check_cost=0.0, ran=False,
                                                reason="not_applicable"))

            if tier > ceiling:
                p_now = voi.combine_probabilities(probs, self.engine.combine_strategy)
                for d in applicable:
                    result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier, p_fail_before=p_now,
                                                p_fail_after=None, voi=0.0, check_cost=0.0, ran=False,
                                                reason="policy_tier_ceiling"))
                continue

            if time.perf_counter() >= deadline:
                p_now = voi.combine_probabilities(probs, self.engine.combine_strategy)
                for d in applicable:
                    result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier, p_fail_before=p_now,
                                                p_fail_after=None, voi=0.0, check_cost=0.0, ran=False,
                                                reason="latency_budget_exhausted"))
                continue

            if tier == Tier.T0:
                eligible = applicable
                decisions = {d.name: (True, 0.0, 0.0, "tier0_always_on") for d in eligible}
            else:
                p_before = voi.combine_probabilities(probs, self.engine.combine_strategy)
                decisions = {}
                for d in applicable:
                    decision = voi.decide_check(
                        p_fail=p_before,
                        cost_fail=cost_fail,
                        cost_mitigate=cost_mitigate,
                        informativeness=d.informativeness,
                        detector_cost_usd=d.est_cost_usd,
                        detector_latency_ms=d.est_latency_ms,
                        lambda_latency=self.engine.policy.lambda_latency,
                        scrutiny=scrutiny,
                    )
                    decisions[d.name] = (decision.run, decision.voi, decision.cost, decision.reason)
                eligible = [d for d in applicable if decisions[d.name][0]]
                for d in applicable:
                    if not decisions[d.name][0]:
                        result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier, p_fail_before=p_before,
                                                    p_fail_after=None, voi=decisions[d.name][1],
                                                    check_cost=decisions[d.name][2], ran=False,
                                                    reason=decisions[d.name][3]))

            if not eligible:
                continue

            remaining_ms = max((deadline - time.perf_counter()) * 1000.0, 0.0)
            tier_timeout = timeout_cfg.get(tier)
            effective_timeout = remaining_ms if tier_timeout is None else min(remaining_ms, max(tier_timeout, 0.0))
            completed, timed_out, _ = await run_detectors_parallel(eligible, ctx, timeout_ms=effective_timeout)
            completed_by_name = {d.name: sig for d, sig in completed}
            p_before = voi.combine_probabilities(probs, self.engine.combine_strategy)
            if tier == Tier.T0:
                p_before_for_trace = p_before
            for d in eligible:
                if d in timed_out:
                    result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier,
                                                p_fail_before=p_before, p_fail_after=None, voi=0.0, check_cost=d.est_cost_usd,
                                                ran=False, reason="tier_timeout"))
                    continue
                sig = completed_by_name.get(d.name)
                if sig is None:
                    result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier,
                                                p_fail_before=p_before, p_fail_after=None, voi=0.0, check_cost=d.est_cost_usd,
                                                ran=False, reason="detector_error"))
                    continue
                sig.p_fail = self.engine._calibrate(sig)
                axis_signals.append(sig)
                result.signals.append(sig)
                probs.append(sig.p_fail)
                p_after = voi.combine_probabilities(probs, self.engine.combine_strategy)
                meta = decisions[d.name]
                result.trace.append(VoIStep(axis=axis, detector=d.name, tier=d.tier,
                                            p_fail_before=p_before, p_fail_after=p_after, voi=meta[1],
                                            check_cost=meta[2], ran=True, reason=meta[3]))
            if tier == Tier.T0:
                p_after_t0 = voi.combine_probabilities(probs, self.engine.combine_strategy)

        p_final = voi.combine_probabilities(probs, self.engine.combine_strategy)
        outcome = AxisOutcome(axis=axis, p_fail=p_final, expected_loss=voi.expected_loss(p_final, cost_fail),
                              signals=axis_signals)
        return outcome, p_after_t0
