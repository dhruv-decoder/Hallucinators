"""The feedback loop: turn human overrides into better-calibrated detectors.

When a human reviews a flagged decision (an escalation or a block) and says whether the response really
was a failure on a given axis, that verdict is ground truth for every detector that fired on that axis.
Accumulating those ``(detector_score, true_label)`` pairs lets us refit each detector's calibrator, so
the probabilities the VoI rule consumes get more honest over time -- which is what stops the system from
over-escalating (alert fatigue) or under-escalating (missed failures).

This closes the loop the brief asks for: flagged/overridden cases improve detection quality over time. It
reuses the calibration in ``cascade/calibration.py`` rather than inventing a new mechanism.

Usage::

    loop = FeedbackLoop()
    # ... a human reviews a decision and records the true label for an axis:
    loop.record_override(result, Axis.PERFORMANCE, is_failure=False)
    # ... after enough reviews, hand refit calibrators to the engine:
    engine.calibrators = loop.calibrators()
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from controlplane.cascade.calibration import (
    Calibrator,
    PlattCalibrator,
    expected_calibration_error,
)
from controlplane.core.types import Axis, CascadeResult


class FeedbackLoop:
    """Accumulates human-labelled detector observations and refits calibrators from them."""

    def __init__(
        self,
        min_samples: int = 30,
        calibrator_factory: Callable[[], Calibrator] = PlattCalibrator,
    ) -> None:
        self.min_samples = min_samples
        self._factory = calibrator_factory
        self._samples: dict[str, list[tuple[float, float]]] = {}

    def record_signal(self, detector_name: str, score: float, is_failure: bool) -> None:
        """Record one labelled observation for a detector."""
        self._samples.setdefault(detector_name, []).append((score, 1.0 if is_failure else 0.0))

    def record_override(self, result: CascadeResult, axis: Axis, is_failure: bool) -> None:
        """Record a human's verdict for one axis of a decision against every detector that fired there."""
        for signal in result.signals:
            if signal.axis == axis:
                self.record_signal(signal.name, signal.score, is_failure)

    def sample_count(self, detector_name: str) -> int:
        return len(self._samples.get(detector_name, []))

    def calibrators(self) -> dict[str, Calibrator]:
        """Fit a calibrator for every detector with at least ``min_samples`` labelled observations.

        Detectors with too little feedback are omitted, so the engine keeps its default (identity) for
        them -- we never fit a calibration curve from a handful of points.
        """
        fitted: dict[str, Calibrator] = {}
        for name, samples in self._samples.items():
            if len(samples) < self.min_samples:
                continue
            scores = np.array([s for s, _ in samples], dtype=float)
            labels = np.array([label for _, label in samples], dtype=float)
            fitted[name] = self._factory().fit(scores, labels)
        return fitted

    def calibration_error(self, detector_name: str) -> tuple[float, float] | None:
        """Return ``(ece_before, ece_after)`` for a detector: raw scores vs its refit calibration.

        Useful for reporting how much a detector's honesty improved. Returns None if there is not yet
        enough feedback to refit.
        """
        samples = self._samples.get(detector_name, [])
        if len(samples) < self.min_samples:
            return None
        scores = np.array([s for s, _ in samples], dtype=float)
        labels = np.array([label for _, label in samples], dtype=float)
        calibrator = self._factory().fit(scores, labels)
        before = expected_calibration_error(scores, labels)
        after = expected_calibration_error(calibrator.predict(scores), labels)
        return before, after
