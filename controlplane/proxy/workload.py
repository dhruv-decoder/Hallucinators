"""The scripted demo traffic and the What-If replay, wired for the proxy.

``demo_prompts`` is what the UI's "Send demo traffic" button (and the ``make traffic`` driver) fire at the
gateway: plain prompts, exactly what a real client sends. Each one lands on a planted scenario in the
simulated upstream (see ``upstream.py``) so the run tells the PLAN section 6 story end to end -- a clean
answer routed down for cost, a confident hallucination auto-repaired, a PII leak blocked, and a fabricated
fact about a named person that lights up two axes at once.

``replay_summary`` runs the What-If simulator (the proof engine) over the labelled synthetic workload under
strict / balanced / lenient appetites plus oversight-off, and returns a JSON-friendly comparison for the
dashboard's Replay panel.
"""

from __future__ import annotations

from controlplane.core.types import Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.demo.workload import synthetic_workload
from controlplane.replay.simulator import WhatIfSimulator


def demo_prompts() -> list[dict]:
    """Plain client prompts that exercise every oversight path (order tells the demo story)."""
    return [
        {"prompt": "What are your customer support hours?", "use_case": "support_bot", "model": "gpt-4o"},
        {"prompt": "How do I reset my password?", "use_case": "support_bot", "model": "gpt-4o"},
        {"prompt": "Where can I download the app?", "use_case": "support_bot", "model": "gpt-4o"},
        {"prompt": "What is the refund window?", "use_case": "support_bot", "model": "gpt-4o"},
        {"prompt": "What is the late payment fee?", "use_case": "support_bot", "model": "gpt-4o"},
        {"prompt": "Who is my account manager and how do I reach them?", "use_case": "support_bot",
         "model": "gpt-4o"},
        {"prompt": "Can you share the customer's payment details?", "use_case": "support_bot",
         "model": "gpt-4o-mini"},
        {"prompt": "What are your customer support hours?", "use_case": "support_bot", "model": "gpt-4o"},
        {"prompt": "How do I roll back a bad deploy? Give me the runbook.", "use_case": "internal_copilot",
         "model": "gpt-4o"},
    ]


def _strict() -> PolicyProfile:
    return PolicyProfile(
        id="support_bot@IN@strict",
        cost_fail={Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0},
        block_threshold=0.7,
        escalate_threshold=0.3,
        annotate_threshold=0.1,
    )


def _balanced() -> PolicyProfile:
    return PolicyProfile(
        id="support_bot@IN@balanced",
        cost_fail={Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0},
        block_threshold=0.85,
        escalate_threshold=0.5,
        annotate_threshold=0.2,
    )


def _lenient() -> PolicyProfile:
    return PolicyProfile(
        id="support_bot@IN@lenient",
        cost_fail={Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0},
        block_threshold=0.9,
        escalate_threshold=0.7,
        annotate_threshold=0.4,
    )


def replay_summary() -> dict:
    """Compare oversight-off vs strict/balanced/lenient over the synthetic workload (What-If proof engine)."""
    sim = WhatIfSimulator(synthetic_workload(), build_engine)
    results = sim.compare({"strict": _strict(), "balanced": _balanced(), "lenient": _lenient()})
    return {
        "scenarios": [
            {
                "name": name,
                "residual_risk": round(r.residual_risk, 5),
                "total_risk": round(r.total_risk, 5),
                "risk_reduction_pct": round(r.risk_reduction_pct, 1),
                "net_usd": round(r.net_usd, 5),
                "cost_saved_usd": round(r.cost_saved_usd, 5),
                "safety_spend_usd": round(r.safety_spend_usd, 5),
                "escalation_rate": round(r.escalation_rate, 3),
                "action_counts": r.action_counts,
                "self_funding": r.net_usd < 0,
            }
            for name, r in results.items()
        ]
    }
