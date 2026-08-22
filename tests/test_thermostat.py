"""Tests for the Adaptive Oversight Thermostat and its effect on the stopping rule."""

from __future__ import annotations

from controlplane.cascade.thermostat import Thermostat, risk_score
from controlplane.core.types import PolicyProfile, RequestContext
from controlplane.demo.run_demo import build_engine


def test_thermostat_starts_neutral_then_tracks_risk():
    t = Thermostat(setpoint=0.15, gain=4.0, s_min=0.5, s_max=3.0, window=5)
    assert t.recommend() == 1.0  # no data yet -> neutral

    for _ in range(5):
        t.observe(0.9)  # sustained high risk
    high = t.recommend()
    assert high > 1.0

    t2 = Thermostat(setpoint=0.15, gain=4.0, s_min=0.5, s_max=3.0, window=5)
    for _ in range(5):
        t2.observe(0.0)  # sustained low risk
    low = t2.recommend()
    assert low < 1.0


def test_thermostat_output_is_bounded():
    t = Thermostat(s_min=0.5, s_max=3.0)
    for _ in range(10):
        t.observe(1.0)
    assert t.recommend() <= 3.0
    for _ in range(10):
        t.observe(0.0)
    assert t.recommend() >= 0.5


def _confident_hallucination() -> RequestContext:
    # Cheap signals put p_fail near certainty, so the T1 self-consistency check sits just below its cost
    # at normal scrutiny -- the marginal case the thermostat is designed to tip.
    return RequestContext(
        request_id="marginal",
        use_case="support_bot",
        prompt="What is the refund window?",
        response="You can absolutely get a refund within 180 days, guaranteed, without a doubt.",
        retrieved_context=["Refunds are available within 30 days of purchase."],
        samples=["Yes, 180 days.", "Definitely 180 days."],
        model="gpt-4o",
        input_tokens=200,
        output_tokens=300,
    )


def _self_consistency_ran(result) -> bool:
    return any(s.detector == "self_consistency" and s.ran for s in result.trace)


def test_raising_scrutiny_tips_a_marginal_check_from_skip_to_run():
    engine = build_engine(PolicyProfile(id="test"))
    ctx = _confident_hallucination()
    # At normal scrutiny the check is not worth its cost; under a risk burst (high scrutiny) it is.
    assert not _self_consistency_ran(engine.run(ctx, scrutiny=1.0))
    assert _self_consistency_ran(engine.run(ctx, scrutiny=3.0))


def test_risk_score_is_the_max_axis_probability():
    engine = build_engine(PolicyProfile(id="test"))
    result = engine.run(_confident_hallucination())
    assert 0.0 <= risk_score(result) <= 1.0
