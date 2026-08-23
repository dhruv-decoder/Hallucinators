"""Tests for conformal risk control of the escaped-failure rate."""

from __future__ import annotations

from controlplane.cascade.conformal import risk_controlled_threshold


def test_separable_scores_certify_low_risk() -> None:
    # Failures score high, clean scores low -> a clean threshold exists.
    scores = [0.9, 0.85, 0.8, 0.95, 0.88] + [0.1, 0.05, 0.2, 0.15, 0.0]
    labels = [True] * 5 + [False] * 5
    cert = risk_controlled_threshold(scores, labels, alpha=0.3)
    assert cert.valid
    assert cert.empirical_fnr <= cert.alpha
    assert cert.risk_bound <= cert.alpha
    assert 0.2 < cert.tau <= 0.8  # flags the failures, not the clean ones


def test_tighter_alpha_flags_more() -> None:
    scores = [0.9, 0.6, 0.55, 0.7, 0.8, 0.65] + [0.1, 0.2, 0.15, 0.05]
    labels = [True] * 6 + [False] * 4
    loose = risk_controlled_threshold(scores, labels, alpha=0.5)
    strict = risk_controlled_threshold(scores, labels, alpha=0.1)
    # A stricter risk budget must not flag less -> a lower-or-equal threshold.
    assert strict.tau <= loose.tau


def test_too_few_failures_cannot_certify() -> None:
    cert = risk_controlled_threshold([0.9, 0.1, 0.2], [True, False, False], alpha=0.1)
    # With one failure, the (n*FNR+1)/(n+1) = 1/2 bound exceeds alpha=0.1 -> not certifiable.
    assert cert.valid is False


def test_no_failures_is_invalid() -> None:
    cert = risk_controlled_threshold([0.1, 0.2], [False, False], alpha=0.1)
    assert cert.valid is False and cert.n_failures == 0
