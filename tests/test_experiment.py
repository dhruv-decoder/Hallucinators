"""Tests for the baseline vs fixed-check vs ControlPlane experiment."""

from __future__ import annotations

from controlplane.core.types import Axis
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.experiment import macro_recall, run_experiment


def test_three_conditions_and_no_oversight_catches_nothing() -> None:
    res = run_experiment(synthetic_labeled_dataset())
    assert set(res) == {"no_oversight", "fixed_checks", "controlplane"}
    none = res["no_oversight"]["confusion"]
    assert none[Axis.PERFORMANCE.value].recall == 0.0  # forwards everything, catches nothing
    assert res["no_oversight"]["added_latency_ms"] == 0.0
    # ControlPlane catches real failures on the performance axis.
    assert res["controlplane"]["confusion"][Axis.PERFORMANCE.value].recall > 0.0


def test_controlplane_never_costs_more_than_fixed_checks() -> None:
    res = run_experiment(synthetic_labeled_dataset())
    cp, fx = res["controlplane"], res["fixed_checks"]
    # VoI can only skip checks fixed-check would run, so it never runs more expensive checks or adds more latency.
    assert cp["expensive_checks_run"] <= fx["expensive_checks_run"]
    assert cp["added_latency_ms"] <= fx["added_latency_ms"] + 1e-6


def test_macro_recall_ignores_empty_axes() -> None:
    from controlplane.eval.metrics import confusion

    cm = {"performance": confusion([True, False], [True, False]),  # recall 1.0
          "responsibility": confusion([False, False], [False, False])}  # no positives -> ignored
    assert macro_recall(cm) == 1.0
