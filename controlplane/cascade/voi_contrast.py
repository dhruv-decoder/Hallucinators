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


# Grounded, but the samples disagree with each other: the cheap tier is split, so the check is worth buying.
_DISAGREE = RequestContext(
    request_id="voi-disagree",
    use_case="support_bot",
    prompt="How long does a refund take to arrive?",
    response="Refunds usually arrive within a few days.",
    retrieved_context=["Refunds are issued within 30 days of an approved request."],
    samples=[
        "Refunds arrive in 3 to 5 business days.",
        "It can take up to 30 days.",
        "Usually about a week, sometimes longer.",
    ],
    model="gpt-4o",
    input_tokens=150,
    output_tokens=40,
)

# Nothing was retrieved, so groundedness has nothing to check against and self-consistency has no samples.
# There is no expensive check to buy at any price: the cascade cannot spend money it has no use for.
_NO_SOURCE = RequestContext(
    request_id="voi-nosource",
    use_case="support_bot",
    prompt="Can you walk me through resetting my password?",
    response="Click 'Forgot password' on the sign-in page and follow the emailed link.",
    retrieved_context=[],
    samples=[],
    model="gpt-4o",
    input_tokens=90,
    output_tokens=30,
)

# Contradicts the source outright and the samples agree with each other on the wrong figure. The cheap tier
# is already confident, so more information cannot change the action: buying a check would be waste.
_CONFIDENT_WRONG = RequestContext(
    request_id="voi-confident-wrong",
    use_case="support_bot",
    prompt="What is the maximum refund window?",
    response="You can absolutely get a refund within 180 days, guaranteed, no doubt about it.",
    retrieved_context=["Refunds are available within 30 days of purchase."],
    samples=[
        "Refunds are available for 180 days.",
        "The window is 180 days.",
    ],
    model="gpt-4o",
    input_tokens=140,
    output_tokens=45,
)

#: Every case, with what its decision demonstrates. Ordered so the table walks from "nothing to buy"
#: through "buy everything" and ends on the subtlest outcome: stopping early because the next check could
#: no longer change the action.
_CASES: list[tuple[str, str, RequestContext]] = [
    (
        "Nothing retrieved",
        "Groundedness has no source to check against, so the only applicable check is worth nothing "
        "and none is bought.",
        _NO_SOURCE,
    ),
    (
        "Grounded, samples agree",
        "The free tier leaves no uncertainty. Every paid check scores zero value and all three are skipped.",
        _SAFE,
    ),
    (
        "Contradicts the source, confidently",
        "Buys both model checks, but skips the sampling check whose price exceeds what its information "
        "is worth here. The rule is per check, not per response.",
        _CONFIDENT_WRONG,
    ),
    (
        "Samples disagree",
        "Genuine uncertainty across the board, so every check earns its cost and all three are bought.",
        _DISAGREE,
    ),
    (
        "Partly grounded and inconsistent",
        "Buys until the axis is settled, then stops: by the time the judge is considered the outcome is "
        "already decided, so its information cannot change the action and it is not paid for.",
        _UNCERTAIN,
    ),
]


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
    """Run every case through the same engine and policy, and report what the stopping rule decided.

    Only the response changes between rows. Everything else -- detectors, thresholds, prices -- is held
    fixed, which is what makes the differing decisions attributable to the rule rather than to configuration.
    """
    cases = [
        {"label": label, "why": why, **_summarize(ctx)} for label, why, ctx in _CASES
    ]
    return {
        "policy_id": _POLICY.id,
        "cases": cases,
        # The original pair, kept so existing callers and tests keep working.
        "safe": next(c for c in cases if c["prompt"] == _SAFE.prompt),
        "uncertain": next(c for c in cases if c["prompt"] == _UNCERTAIN.prompt),
        "note": (
            "Same engine, detectors, and policy across every row. The stopping rule buys the expensive check "
            "only where the cheap checks leave enough uncertainty that the information is worth more than the "
            "check costs."
        ),
    }
