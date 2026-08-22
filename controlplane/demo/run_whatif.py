"""What-If / Replay demo: the same workload under different oversight policies.

Runs the support-bot workload from ``run_demo`` under three risk appetites (strict / balanced / lenient)
and against an "oversight off" baseline, then prints how residual risk, escalation load, and net cost
trade off. This is the "hit Replay to prove it" moment: it shows, on identical traffic, what ControlPlane
buys versus doing nothing, and how the policy dial moves the safety/human-load/cost balance.

Run with ``make whatif`` or ``python -m controlplane.demo.run_whatif``.
"""

from __future__ import annotations

from controlplane.core.types import PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.demo.workload import synthetic_workload
from controlplane.replay import ScenarioResult, WhatIfSimulator


def policies() -> dict[str, PolicyProfile]:
    """Three risk appetites. The risk model (cost_fail) is held constant so only appetite varies:
    strict acts aggressively (low thresholds), lenient forwards more (high thresholds)."""
    return {
        "strict": PolicyProfile(id="strict", block_threshold=0.6, escalate_threshold=0.25, annotate_threshold=0.1),
        "balanced": PolicyProfile(id="balanced"),  # defaults: 0.85 / 0.5 / 0.2
        "lenient": PolicyProfile(id="lenient", block_threshold=0.97, escalate_threshold=0.75, annotate_threshold=0.5),
    }


def _print_row(r: ScenarioResult) -> None:
    actions = ", ".join(f"{k}={v}" for k, v in sorted(r.action_counts.items()))
    print(
        f"  {r.name:14s} | residual risk {r.residual_risk:6.3f} "
        f"(-{r.risk_reduction_pct:4.0f}%) | escalate {r.escalation_rate*100:3.0f}% "
        f"| saved ${r.cost_saved_usd:.4f} | spend ${r.safety_spend_usd:.4f} "
        f"| net ${r.net_usd:+.4f}"
    )
    print(f"                 | actions: {actions}")


def main() -> None:
    simulator = WhatIfSimulator(synthetic_workload(), build_engine)
    results = simulator.compare(policies())

    print("ControlPlane What-If / Replay -- same support-bot workload, different oversight")
    print("=" * 78)
    print("Residual risk = model-estimated expected loss of answers that still reach users (lower safer).")
    print("Risk numbers are ControlPlane's own estimates, not measured against ground truth.\n")

    for name in ["oversight_off", "strict", "balanced", "lenient"]:
        _print_row(results[name])
        print()

    off = results["oversight_off"]
    balanced = results["balanced"]
    print("=" * 78)
    print(
        f"Balanced vs oversight off: residual risk {off.residual_risk:.3f} -> "
        f"{balanced.residual_risk:.3f} (a {balanced.risk_reduction_pct:.0f}% cut), "
        f"at a net cost of ${balanced.net_usd:+.4f} "
        + ("(self-funding)" if balanced.net_usd < 0 else "")
    )


if __name__ == "__main__":
    main()
