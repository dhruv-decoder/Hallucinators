"""Tests for the override -> recalibrate feedback loop."""

from __future__ import annotations

from controlplane.core.types import Action, Axis, CascadeResult, Signal, Tier
from controlplane.demo.run_feedback import _engine, _human_reviewed_outcomes
from controlplane.feedback import FeedbackLoop


def test_calibrators_require_minimum_feedback():
    loop = FeedbackLoop(min_samples=30)
    for _ in range(10):
        loop.record_signal("overconfidence", 0.7, True)
    assert loop.calibrators() == {}  # too few samples to fit


def test_record_override_only_touches_the_named_axis():
    loop = FeedbackLoop()
    result = CascadeResult(request_id="r", use_case="u")
    result.signals.append(Signal(name="overconfidence", axis=Axis.PERFORMANCE, tier=Tier.T0, score=0.7))
    result.signals.append(Signal(name="regex_pii", axis=Axis.RESPONSIBILITY, tier=Tier.T0, score=0.9))
    loop.record_override(result, Axis.PERFORMANCE, is_failure=False)
    assert loop.sample_count("overconfidence") == 1
    assert loop.sample_count("regex_pii") == 0


def test_feedback_reduces_calibration_error():
    loop = FeedbackLoop(min_samples=30)
    _human_reviewed_outcomes(loop, n=300)
    before, after = loop.calibration_error("overconfidence")
    assert after < before


def test_learned_calibration_downgrades_a_false_escalation():
    ctx_result_before = _engine().run(_confident_but_fine())
    assert ctx_result_before.action == Action.ESCALATE

    loop = FeedbackLoop(min_samples=30)
    _human_reviewed_outcomes(loop, n=300)
    engine = _engine()
    engine.calibrators = loop.calibrators()
    after = engine.run(_confident_but_fine())
    assert after.action != Action.ESCALATE  # the over-flag is corrected


def _confident_but_fine():
    from controlplane.core.types import RequestContext

    return RequestContext(
        request_id="confident-but-fine",
        use_case="support_bot",
        prompt="Is the store open on Sunday?",
        response="Yes, absolutely, this is definitely guaranteed correct.",
        retrieved_context=["Yes, absolutely, this is definitely guaranteed correct."],
        model="gpt-4o",
        input_tokens=40,
        output_tokens=20,
    )
