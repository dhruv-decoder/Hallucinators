"""Tests for the confidence intervals added in P1.3: Wilson for proportions, bootstrap for F1."""

from __future__ import annotations

from controlplane.eval.metrics import bootstrap_f1_ci, confusion, wilson_interval


def test_wilson_interval_brackets_the_point_estimate() -> None:
    lo, hi = wilson_interval(76, 100)
    assert lo < 0.76 < hi
    assert (round(lo, 2), round(hi, 2)) == (0.67, 0.83)  # standard textbook value for 76/100


def test_wilson_interval_edge_cases() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)          # empty denominator -> no interval
    lo, hi = wilson_interval(5, 5)                       # extreme p stays inside [0, 1] and is asymmetric
    assert 0.0 <= lo < 1.0 and hi == 1.0
    lo0, hi0 = wilson_interval(0, 5)
    assert lo0 == 0.0 and 0.0 < hi0 < 1.0


def test_bootstrap_f1_ci_is_deterministic_and_contains_the_point() -> None:
    y_true = [True] * 40 + [False] * 60
    y_pred = [True] * 30 + [False] * 10 + [True] * 5 + [False] * 55
    point = confusion(y_true, y_pred).f1
    lo, hi = bootstrap_f1_ci(y_true, y_pred, n_boot=1000, seed=0)
    assert lo < point < hi
    assert bootstrap_f1_ci(y_true, y_pred, n_boot=1000, seed=0) == (lo, hi)  # seeded -> reproducible
    assert bootstrap_f1_ci([], [], n_boot=100) == (0.0, 0.0)


def test_confusion_matrix_recall_and_precision_cis() -> None:
    cm = confusion([True] * 8 + [False] * 2, [True] * 6 + [False] * 2 + [True] * 1 + [False] * 1)
    r_lo, r_hi = cm.recall_ci()
    p_lo, p_hi = cm.precision_ci()
    assert r_lo <= cm.recall <= r_hi
    assert p_lo <= cm.precision <= p_hi
