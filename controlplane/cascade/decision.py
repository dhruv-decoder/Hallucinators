"""Reference action selection.

Given the engine's final per-axis failure probabilities and the active policy, choose one action:
pass / annotate / escalate / block. This is a deliberately simple reference implementation so the core
pipeline runs end to end; P2's policy engine replaces it with the full config-driven version (per
use-case / geography / risk appetite) described in docs/PLAN.md.

AUTO_REPAIR is intentionally not emitted yet: a faithful repair needs a corrective generation, which
arrives with the model/proxy layer. Emitting it now would be a fabricated capability. Tracked as a TODO
for the policy engine.
"""

from __future__ import annotations

from controlplane.core.types import Action, Axis, AxisOutcome, PolicyProfile


def decide_action(
    per_axis: dict[Axis, AxisOutcome], policy: PolicyProfile
) -> tuple[Action, str]:
    """Return ``(action, reason)`` from the per-axis outcomes and the policy thresholds.

    Rules, in order of severity:

    1. A responsibility failure above the block threshold is a clear violation (PII leak, unsafe) -> BLOCK.
    2. Any other axis above the block threshold is high-stakes but not a clean block -> ESCALATE to a human.
    3. Any axis above the escalate threshold -> ESCALATE.
    4. Any axis above the annotate threshold -> ANNOTATE with a caveat.
    5. Otherwise -> PASS.
    """
    resp = per_axis.get(Axis.RESPONSIBILITY)
    if resp is not None and resp.p_fail >= policy.block_threshold:
        return Action.BLOCK, f"responsibility p_fail={resp.p_fail:.2f} >= block {policy.block_threshold}"

    worst_axis, worst_p = _worst(per_axis)
    if worst_axis is None:
        return Action.PASS, "no axis assessed"

    if worst_p >= policy.block_threshold:
        return Action.ESCALATE, f"{worst_axis.value} p_fail={worst_p:.2f} high-stakes, uncertain"
    if worst_p >= policy.escalate_threshold:
        return Action.ESCALATE, f"{worst_axis.value} p_fail={worst_p:.2f} >= escalate {policy.escalate_threshold}"
    if worst_p >= policy.annotate_threshold:
        return Action.ANNOTATE, f"{worst_axis.value} p_fail={worst_p:.2f} >= annotate {policy.annotate_threshold}"
    return Action.PASS, f"all axes below annotate threshold (worst {worst_p:.2f})"


def _worst(per_axis: dict[Axis, AxisOutcome]) -> tuple[Axis | None, float]:
    """Return the axis with the highest failure probability and that probability."""
    worst_axis: Axis | None = None
    worst_p = -1.0
    for axis, outcome in per_axis.items():
        if outcome.p_fail > worst_p:
            worst_p = outcome.p_fail
            worst_axis = axis
    return worst_axis, max(worst_p, 0.0)
