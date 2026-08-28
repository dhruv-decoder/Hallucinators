"""Tests for offline detector-informativeness (eta) fitting and safe runtime artifacts."""

from __future__ import annotations

import json

from controlplane.cascade.informativeness import EtaEstimate, apply_artifact, bootstrap_ci, estimate_eta, load_artifact, save_artifact
from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier


class _Detector(Detector):
    name = "test_detector"
    axis = Axis.PERFORMANCE
    tier = Tier.T1
    informativeness = 0.8

    def assess(self, ctx: RequestContext):
        return 0.0, {}


def test_eta_is_bounded_and_data_driven() -> None:
    rows = [
        (0.8, 0.2, True),
        (0.7, 0.3, False),
        (0.9, 0.4, True),
    ] * 50
    estimate = estimate_eta(rows, prior=0.8, min_samples=20)
    assert estimate.fallback is False
    assert 0.0 <= estimate.eta <= 1.0
    assert estimate.n_samples >= 20


def test_insufficient_samples_fall_back_to_manual_prior() -> None:
    estimate = estimate_eta([(0.8, 0.2, True)] * 3, prior=0.73, min_samples=10)
    assert estimate.fallback is True
    assert estimate.eta == 0.73


def test_eta_fit_is_deterministic_for_same_rows() -> None:
    rows = [(0.8, 0.4, True), (0.2, 0.1, False)] * 50
    a = estimate_eta(rows, prior=0.8, min_samples=20)
    b = estimate_eta(rows, prior=0.8, min_samples=20)
    assert a.eta == b.eta
    assert a.numerator == b.numerator
    assert a.denominator == b.denominator


def test_eta_artifact_round_trip_and_runtime_override(tmp_path) -> None:
    estimate = EtaEstimate(
        detector="test_detector", prior=0.8, eta=0.61, n_samples=120,
        numerator=1.0, denominator=1.64, source="test", split="fit",
        min_samples=20, fallback=False, bootstrap_low=0.55, bootstrap_high=0.67,
    )
    path = tmp_path / "eta.json"
    save_artifact(path, {estimate.detector: estimate}, dataset="test", fit_split="20%", holdout_split="20%")
    data = load_artifact(path)
    detector = _Detector()
    applied = apply_artifact([detector], data)
    assert applied == {"test_detector": 0.61}
    assert detector.informativeness == 0.61
    payload = json.loads(path.read_text())
    assert payload["dataset"] == "test"
    assert payload["estimates"]["test_detector"]["bootstrap_low"] == 0.55


def test_bootstrap_ci_returns_bounded_interval() -> None:
    rows = [(0.8, 0.3, True), (0.6, 0.1, False)] * 20
    low, high = bootstrap_ci(rows, n_boot=200)
    assert 0.0 <= low <= high <= 1.0
