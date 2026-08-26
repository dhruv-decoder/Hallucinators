"""Tests for the live-calibration fitting path."""

from __future__ import annotations

from controlplane.cascade.calibrate_live import collect_scores, fit_live_calibrators
from controlplane.eval.dataset import synthetic_labeled_dataset


def test_collect_scores_gathers_per_detector_pairs() -> None:
    per = collect_scores(synthetic_labeled_dataset())
    assert "groundedness_heuristic" in per
    scores, labels = per["groundedness_heuristic"]
    assert len(scores) == len(labels) and len(scores) > 0
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_tiny_seed_falls_back_to_identity() -> None:
    # The 18-example seed is below the min-points gate, so nothing is calibrated (safe identity fallback).
    assert fit_live_calibrators(synthetic_labeled_dataset()) == {}


def test_calibrates_when_enough_data_and_keeps_no_signal_low() -> None:
    # Replicate the seed to clear the min-points gate; the fitted calibrator must keep score 0 low.
    big = synthetic_labeled_dataset() * 4
    cals = fit_live_calibrators(big, min_points=20)
    assert cals, "expected at least one detector to calibrate with enough data"
    for cal in cals.values():
        assert cal.predict_one(0.0) < 0.25
