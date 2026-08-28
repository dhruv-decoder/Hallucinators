"""The VoI skip-vs-buy contrast -- the single clearest proof that oversight is *adaptive*.

Two responses go through the **same** engine, the **same** detectors, and the **same** policy. The only
difference is the response itself:

- a **safe** response (well-grounded, samples agree) -- the cheap T0 checks already make failure very
  unlikely, so the value of buying the expensive T1 check is below its cost and the VoI rule **SKIPS** it.
- an **uncertain** response (poorly grounded, samples disagree) -- the T0 checks leave real uncertainty,
  so an extra check is worth more than it costs and the VoI rule **BUYS** it.

Nothing here is scripted: both traces are produced live by ``CascadeEngine.run`` with the same code the
proxy uses. This is deterministic and needs no API key or model download, so it is safe to demo. (When the
HHEM model tier is installed the same contrast holds with HHEM as the bought check; offline the bought check
is self-consistency.)
"""

from __future__ import annotations

from controlplane.cascade.detectors.factory import build_cost_detectors, build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile, RequestContext

# The same balanced customer-support policy the live proxy uses by default (see proxy/oversight.py).
_POLICY = PolicyProfile(
    id="support_bot@IN@balanced",
    cost_fail={Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0},
    cost_mitigate={Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10},
    block_threshold=0.85,
    escalate_threshold=0.5,
    annotate_threshold=0.2,
)

# A safe, well-grounded answer with samples that agree: the cheap checks already clear it.
_SAFE = RequestContext(
    request_id="voi-safe",
    use_case="support_bot",
    prompt="What are your customer support hours?",
    response="Support is available 9am to 6pm, Monday to Friday.",
    retrieved_context=["Support is available 9am to 6pm, Monday to Friday."],
    samples=[
        "Support is available 9am to 6pm, Monday to Friday.",
        "We're open 9am to 6pm on weekdays.",
    ],
    model="gpt-4o",
    input_tokens=180,
    output_tokens=40,
)

# An uncertain answer: only partly grounded ("around $40" vs a $25 source) and the samples disagree.
_UNCERTAIN = RequestContext(
    request_id="voi-uncertain",
    use_case="support_bot",
    prompt="What is the late payment fee?",
    response="The late fee is around $40.",
    retrieved_context=["The late fee is $25, charged after 15 days."],
    samples=[
        "The late fee is $25.",
        "I think it's about $40 plus interest.",
        "Roughly $25, but it may vary.",
    ],
    model="gpt-4o",
    input_tokens=160,
    output_tokens=45,
)


def _engine() -> CascadeEngine:
    return CascadeEngine(
        detectors=build_failure_detectors(),
        cost_detectors=build_cost_detectors(),
        policy=_POLICY,
    )


def _summarize(ctx: RequestContext) -> dict:
    """Run one case and pull out the expensive (tier>0) decisions the VoI rule actually made."""
    result = _engine().run(ctx)
    expensive = [
        {
            "detector": s.detector,
            "tier": int(s.tier),
            "ran": s.ran,
            "p_fail_before": round(s.p_fail_before, 4),
            "voi": round(s.voi, 6),
            "check_cost": round(s.check_cost, 6),
            "reason": s.reason,
        }
        for s in result.trace
        if int(s.tier) > 0 and s.reason != "not_applicable"
    ]
    perf = result.per_axis.get(Axis.PERFORMANCE)
    return {
        "prompt": ctx.prompt,
        "response": ctx.response,
        "p_fail_after_t0": round(
            next((s.p_fail_before for s in result.trace if int(s.tier) > 0), perf.p_fail if perf else 0.0), 4
        ),
        "final_p_fail": round(perf.p_fail, 4) if perf else 0.0,
        "action": result.action.value,
        "expensive_checks": expensive,
        "bought_a_check": any(s["ran"] for s in expensive),
        "stopping_reason": result.stopping_reason,
    }


def voi_contrast() -> dict:
    """Return the two-case contrast: same engine/policy, safe response SKIPS the check, uncertain BUYS it."""
    return {
        "policy_id": _POLICY.id,
        "safe": _summarize(_SAFE),
        "uncertain": _summarize(_UNCERTAIN),
        "note": (
            "Same engine, detectors, and policy. The VoI rule buys the expensive check only when the cheap "
            "checks leave enough uncertainty that the information is worth more than the check's cost."
        ),
    }
