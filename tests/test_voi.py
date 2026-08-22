"""Tests for the value-of-information decision core."""

from __future__ import annotations

import numpy as np

from controlplane.cascade import voi


def test_value_of_information_is_never_negative():
    """A check can never be worth less than nothing: VoI >= 0 over the whole parameter grid."""
    for p in np.linspace(0.0, 1.0, 11):
        for cost_fail in [0.1, 1.0, 5.0]:
            for cost_mitigate in [0.01, 0.05, 0.5, 2.0]:
                for eta in [0.0, 0.3, 1.0]:
                    v = voi.value_of_information(p, cost_fail, cost_mitigate, eta)
                    assert v >= -1e-12


def test_voi_zero_when_mitigation_costs_more_than_failure():
    """If mitigating costs more than the failure itself, information has no value."""
    v = voi.value_of_information(p_fail=0.5, cost_fail=1.0, cost_mitigate=2.0, informativeness=1.0)
    assert v == 0.0


def test_voi_zero_at_certainty():
    """At p=0 or p=1 there is no uncertainty for a check to resolve on the pass side."""
    assert voi.value_of_information(0.0, 1.0, 0.05, 1.0) == 0.0


def test_bayes_risk_takes_the_cheaper_action():
    # When the risk of passing is below the mitigation cost, we would pass.
    assert voi.bayes_risk(0.01, 1.0, 0.05) == 0.01
    # When it exceeds the mitigation cost, we would mitigate.
    assert voi.bayes_risk(0.9, 1.0, 0.05) == 0.05


def test_decide_check_runs_only_when_worth_it():
    run = voi.decide_check(
        p_fail=0.4, cost_fail=1.0, cost_mitigate=0.05, informativeness=0.6,
        detector_cost_usd=0.0, detector_latency_ms=1.0, lambda_latency=1e-6,
    )
    assert run.run is True and run.voi > run.cost

    skip = voi.decide_check(
        p_fail=0.4, cost_fail=1.0, cost_mitigate=0.05, informativeness=0.6,
        detector_cost_usd=1.0, detector_latency_ms=1.0, lambda_latency=1e-6,
    )
    assert skip.run is False and skip.voi < skip.cost


def test_combine_probabilities():
    assert voi.combine_probabilities([]) == 0.0
    assert voi.combine_probabilities([0.5, 0.5], "max") == 0.5
    assert abs(voi.combine_probabilities([0.5, 0.5], "mean") - 0.5) < 1e-9
    # noisy-OR: 1 - (1-0.5)(1-0.5) = 0.75
    assert abs(voi.combine_probabilities([0.5, 0.5], "noisy_or") - 0.75) < 1e-9
