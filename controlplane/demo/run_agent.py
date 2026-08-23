"""Agentic finale demo: a tool-calling agent compounds a hallucination and the auditor aborts it.

Runs the scripted trajectory (``controlplane/agent/scenarios.py``) twice:

- **oversight off** -- every planned step executes; the agent loops on its own invention and hands the user a
  confidently wrong answer; full token cost is paid.
- **oversight on** -- the trajectory auditor watches risk compound across steps and aborts mid-run, escalating
  to a human, so the wrong answer never reaches the user and the wasted steps are never paid for.

Run with ``make agent`` or ``python -m controlplane.demo.run_agent``. No API keys or downloads needed.
"""

from __future__ import annotations

from controlplane.agent import TrajectoryAuditor
from controlplane.agent.scenarios import TASK, compounding_hallucination_trajectory
from controlplane.pnl.pricing import Pricing
from controlplane.proxy.oversight import default_policies


def _oversight_off_cost(steps) -> tuple[float, str]:
    """What the agent costs and answers with no oversight: every step runs, wrong answer reaches the user."""
    pricing = Pricing()
    total = sum(pricing.cost(s.model, s.input_tokens, s.output_tokens) for s in steps)
    final_answer = next((s.response for s in reversed(steps) if s.response), "")
    return total, final_answer


def main() -> None:
    policy = default_policies()["support_bot"]
    steps = compounding_hallucination_trajectory()

    print("Agentic oversight demo -- a support agent compounding a hallucination")
    print("=" * 74)
    print(f"TASK: {TASK}\n")

    off_cost, off_answer = _oversight_off_cost(steps)
    print("[ oversight OFF ]")
    print(f"  all {len(steps)} steps run; agent loops and answers the user:")
    print(f"  → \"{off_answer}\"   (WRONG: the real window is 30 days)")
    print(f"  agent spend: ${off_cost:.5f}\n")

    auditor = TrajectoryAuditor(policy=policy)
    rec = auditor.audit(TASK, steps)
    print("[ oversight ON ]")
    for v in rec.verdicts:
        tag = {"continue": "  ok  ", "escalate": " flag ", "abort": " STOP "}[v.action]
        loop = f" loop x{v.loop_repeat}" if v.loop_repeat >= 2 else ""
        print(
            f"  [{tag}] step {v.index}: risk={v.step_risk:.2f} cumulative={v.cumulative_risk:.2f}{loop}"
            f"  ({v.reason})"
        )
    print(f"\n  {rec.summary}")
    print(
        f"  executed {rec.n_steps_executed}/{rec.n_steps_planned} steps, escalated to a human, "
        f"wrong answer NEVER reached the user."
    )
    print(f"  agent spend avoided (waste-killer): ${rec.wasted_usd:.5f}")


if __name__ == "__main__":
    main()
