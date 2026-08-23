"""The trajectory auditor: run the three-axis cascade on every agent step, plus trajectory-level checks.

Per step it reuses the ordinary :class:`CascadeEngine` (an agent step is just another monitored call). On top
of that it tracks three things that only exist across steps:

- **compounding risk** -- a running sum of each step's risk. An early hallucination that shapes later steps
  shows up as risk that keeps accumulating; when it crosses the policy's ``risk_budget`` the trajectory is
  judged *unrecoverable* and aborted. Crucially we do **not** abort on the first blip -- single early errors
  often self-correct; we abort on the compounding one (the 2026 "unrecoverable vs first-error" insight).
- **loops** -- the same tool called with the same arguments produces no new information; repeated signatures
  above ``loop_threshold`` mark the agent as stuck.
- **waste** -- every repeated (no-progress) step, and every planned step we skip by aborting early, is money
  saved. That is the agent "waste-killer": the cheapest bad trajectory is the one you stop early.

Aborting stops executing further steps, so the tokens for the rest of the run are never spent -- booked as
``wasted_usd`` saved. Each executed step is written to the flight recorder as an ordinary receipt (use case
``agent``) so agent oversight shows up in the same live feed and audit trail as everything else.
"""

from __future__ import annotations

import uuid

from controlplane.agent.types import AgentStep, StepVerdict, TrajectoryReceipt
from controlplane.cascade.detectors import (
    GroundednessHeuristicDetector,
    OverconfidenceDetector,
    PromptInjectionDetector,
    RegexPiiDetector,
    UnsafeContentDetector,
)
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile, RequestContext
from controlplane.pnl.pricing import Pricing
from controlplane.recorder import JsonlRecorder


def _default_engine(policy: PolicyProfile) -> CascadeEngine:
    """A per-step engine. Groundedness checks each step's claim against the tool observation it came from."""
    return CascadeEngine(
        detectors=[
            OverconfidenceDetector(),
            GroundednessHeuristicDetector(),
            RegexPiiDetector(),
            PromptInjectionDetector(),
            UnsafeContentDetector(),
        ],
        policy=policy,
    )


class TrajectoryAuditor:
    """Oversee a whole agent trajectory, aborting on the unrecoverable compounding failure."""

    def __init__(
        self,
        policy: PolicyProfile | None = None,
        engine: CascadeEngine | None = None,
        recorder: JsonlRecorder | None = None,
        pricing: Pricing | None = None,
        risk_budget: float = 1.2,
        loop_threshold: int = 2,
    ) -> None:
        self.policy = policy or PolicyProfile()
        self.engine = engine or _default_engine(self.policy)
        self.recorder = recorder
        self.pricing = pricing or Pricing()
        self.risk_budget = risk_budget
        self.loop_threshold = loop_threshold

    def audit(self, task: str, steps: list[AgentStep]) -> TrajectoryReceipt:
        """Run the trajectory under oversight, stopping the moment it becomes unrecoverable."""
        trajectory_id = f"traj-{uuid.uuid4().hex[:8]}"
        seen: dict[str, int] = {}
        cumulative_risk = 0.0
        wasted_steps = 0
        verdicts: list[StepVerdict] = []
        aborted_at: int | None = None
        final_action = "completed"

        for step in steps:
            # -- per-step cascade: the step's claim is checked against the observation it came from --
            ctx = RequestContext(
                request_id=f"{trajectory_id}-s{step.index}",
                use_case="agent",
                prompt=f"{task}\n\nthought: {step.thought}\ntool_input: {step.tool_input}",
                response=step.response or step.observation,
                retrieved_context=[step.observation] if step.observation else [],
                model=step.model,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
            )
            result = self.engine.run(ctx)
            per_axis = {ax: round(o.p_fail, 4) for ax, o in result.per_axis.items()}
            step_risk = max(per_axis.values(), default=0.0)
            cumulative_risk += step_risk

            # -- trajectory-level signals --
            sig = step.signature()
            seen[sig] = seen.get(sig, 0) + 1 if step.tool else 0
            loop_repeat = seen.get(sig, 0)
            wasted = bool(step.tool) and loop_repeat > 1
            if wasted:
                wasted_steps += 1

            resp_p = per_axis.get(Axis.RESPONSIBILITY, 0.0)
            action, reason = self._decide(step_risk, cumulative_risk, loop_repeat, resp_p)

            receipt_id = ctx.request_id
            if self.recorder is not None:
                from controlplane.pnl import PnlLedger

                pnl = PnlLedger().book(ctx, result)
                rec = self.recorder.record(result, pnl, policy_id=self.policy.id)
                receipt_id = rec.request_id

            verdicts.append(
                StepVerdict(
                    index=step.index,
                    per_axis_p_fail=per_axis,
                    step_risk=round(step_risk, 4),
                    cumulative_risk=round(cumulative_risk, 4),
                    loop_repeat=loop_repeat,
                    wasted=wasted,
                    action=action,
                    reason=reason,
                    receipt_id=receipt_id,
                )
            )

            if action == "abort":
                aborted_at = step.index
                final_action = "blocked" if resp_p >= self.policy.block_threshold else "escalated"
                break

        executed = len(verdicts)
        # Waste-killer: the planned steps we never ran because we aborted are money saved.
        wasted_usd = 0.0
        if aborted_at is not None:
            for skipped in steps[executed:]:
                wasted_usd += self.pricing.cost(skipped.model, skipped.input_tokens, skipped.output_tokens)

        return TrajectoryReceipt(
            trajectory_id=trajectory_id,
            task=task,
            n_steps_planned=len(steps),
            n_steps_executed=executed,
            aborted_at=aborted_at,
            final_action=final_action,
            cumulative_risk=round(cumulative_risk, 4),
            wasted_steps=wasted_steps,
            wasted_usd=round(wasted_usd, 6),
            verdicts=verdicts,
            summary=self._summary(final_action, aborted_at, len(steps), executed, wasted_usd),
        )

    def _decide(
        self, step_risk: float, cumulative_risk: float, loop_repeat: int, resp_p: float
    ) -> tuple[str, str]:
        """Continue / escalate / abort for one step, per the trajectory-level rules."""
        if resp_p >= self.policy.block_threshold:
            return "abort", f"unsafe/leaking step (responsibility {resp_p:.2f}) -> block"
        # A loop while uncertain is the clearest "unrecoverable" signal -- the agent is confirming its own
        # invention with no new information -- so it is checked before raw compounding.
        if loop_repeat >= self.loop_threshold and step_risk >= self.policy.escalate_threshold:
            return "abort", (
                f"loop x{loop_repeat} while uncertain ({step_risk:.2f}), cumulative risk "
                f"{cumulative_risk:.2f} -> escalate"
            )
        if cumulative_risk >= self.risk_budget:
            return "abort", f"compounding risk {cumulative_risk:.2f} >= budget {self.risk_budget} -> escalate"
        if step_risk >= self.policy.escalate_threshold:
            return "escalate", f"step risk {step_risk:.2f} high but trajectory still recoverable"
        return "continue", "within budget"

    @staticmethod
    def _summary(final_action: str, aborted_at: int | None, planned: int, executed: int, saved: float) -> str:
        if aborted_at is None:
            return f"trajectory completed under oversight ({executed} steps, within risk budget)"
        verb = "blocked" if final_action == "blocked" else "escalated to a human"
        return (
            f"aborted at step {aborted_at} and {verb}: stopped a compounding failure after {executed} of "
            f"{planned} planned steps, saving ${saved:.5f} in avoided agent spend"
        )
