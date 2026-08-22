"""Tests for probability calibration."""

from __future__ import annotations

import numpy as np

from controlplane.cascade import calibration as cal


def _miscalibrated_dataset(n: int = 5000, seed: int = 0):
    """Raw scores that overstate risk: the true failure rate is score**2, not score."""
    rng = np.random.default_rng(seed)
    scores = rng.uniform(0.0, 1.0, size=n)
    labels = (rng.uniform(0.0, 1.0, size=n) < scores**2).astype(float)
    return scores, labels


def test_platt_reduces_calibration_error():
    scores, labels = _miscalibrated_dataset()
    ece_raw = cal.expected_calibration_error(scores, labels)
    platt = cal.PlattCalibrator().fit(scores, labels)
    ece_platt = cal.expected_calibration_error(platt.predict(scores), labels)
    assert ece_platt < ece_raw


def test_isotonic_reduces_calibration_error_and_is_monotone():
    scores, labels = _miscalibrated_dataset()
    ece_raw = cal.expected_calibration_error(scores, labels)
    iso = cal.IsotonicCalibrator().fit(scores, labels)
    grid = np.linspace(0.0, 1.0, 50)
    preds = iso.predict(grid)
    assert np.all(np.diff(preds) >= -1e-9)  # non-decreasing
    ece_iso = cal.expected_calibration_error(iso.predict(scores), labels)
    assert ece_iso < ece_raw


def test_pav_is_monotone():
    out = cal._pav(np.array([3.0, 1.0, 2.0]))
    assert np.all(np.diff(out) >= -1e-9)
    assert np.allclose(out, [2.0, 2.0, 2.0])


def test_ece_zero_when_perfectly_calibrated():
    probs = np.array([0.0, 0.0, 1.0, 1.0])
    labels = np.array([0.0, 0.0, 1.0, 1.0])
    assert cal.expected_calibration_error(probs, labels) == 0.0


def test_identity_calibrator_clamps():
    ident = cal.IdentityCalibrator()
    assert ident.predict_one(0.5) == 0.5
    assert ident.predict_one(1.5) == 1.0
    assert ident.predict_one(-0.2) == 0.0
