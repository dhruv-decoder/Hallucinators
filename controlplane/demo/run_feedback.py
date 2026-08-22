"""Feedback-loop demo: human overrides make an over-flagging detector honest.

The overconfidence detector fires on assertive language, but assertive answers are only sometimes wrong,
so its raw score over-states risk and causes false escalations (alert fatigue). Here a batch of
human-reviewed outcomes is fed back; the loop refits the detector's calibration; its calibration error
drops; and a confident-but-correct answer that used to be escalated is no longer.

Run with ``python -m controlplane.demo.run_feedback``.
"""

from __future__ import annotations

import numpy as np

from controlplane.cascade.detectors import (
    GroundednessHeuristicDetector,
    ModelOverkillDetector,
    OverconfidenceDetector,
    RegexPiiDetector,
    SelfConsistencyDetector,
    SemanticCacheDetector,
)
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import PolicyProfile, RequestContext
from controlplane.feedback import FeedbackLoop


def _engine() -> CascadeEngine:
    detectors = [
        OverconfidenceDetector(),
        GroundednessHeuristicDetector(),
        SelfConsistencyDetector(),
        RegexPiiDetector(),
    ]
    cost = [ModelOverkillDetector(), SemanticCacheDetector()]
    return CascadeEngine(detectors, cost, PolicyProfile(id="support_bot@IN@balanced"))


def _human_reviewed_outcomes(loop: FeedbackLoop, n: int = 300, seed: int = 0) -> None:
    """Simulate n human reviews of confident answers. The overconfidence score over-states risk:
    an answer flagged at score s is actually wrong only about 0.4*s of the time."""
    rng = np.random.default_rng(seed)
    scores = rng.uniform(0.3, 0.9, size=n)
    labels = rng.uniform(0.0, 1.0, size=n) < (0.4 * scores)
    for score, label in zip(scores, labels, strict=True):
        loop.record_signal("overconfidence", float(score), bool(label))


def main() -> None:
    # A confident but well-grounded (correct) answer: overconfidence fires, nothing else does.
    ctx = RequestContext(
        request_id="confident-but-fine",
        use_case="support_bot",
        prompt="Is the store open on Sunday?",
        response="Yes, absolutely, this is definitely guaranteed correct.",
        retrieved_context=["Yes, absolutely, this is definitely guaranteed correct."],
        model="gpt-4o",
        input_tokens=40,
        output_tokens=20,
    )

    print("Feedback loop: human overrides recalibrate an over-flagging detector")
    print("=" * 68)

    before = _engine().run(ctx)
    print(f"Before feedback: action = {before.action.value.upper()} "
          f"(overconfidence uncalibrated -> over-flags)")

    loop = FeedbackLoop(min_samples=30)
    _human_reviewed_outcomes(loop)
    ece = loop.calibration_error("overconfidence")
    if ece:
        print(f"After {loop.sample_count('overconfidence')} human reviews: "
              f"overconfidence calibration error {ece[0]:.3f} -> {ece[1]:.3f}")

    engine = _engine()
    engine.calibrators = loop.calibrators()
    after = engine.run(ctx)
    print(f"After feedback:  action = {after.action.value.upper()} "
          f"(calibrated risk is lower, so the false escalation is avoided)")

    print("=" * 68)
    print("The loop reused the same response and the same detector -- only the learned calibration")
    print("changed, turning a confident-but-correct answer from an escalation into a lighter action.")


if __name__ == "__main__":
    main()
