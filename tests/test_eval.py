"""Tests for the evaluation harness and its metrics."""

from __future__ import annotations

from controlplane.core.types import Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.harness import run_harness
from controlplane.eval.metrics import confusion


def _report():
    return run_harness(
        lambda: build_engine(PolicyProfile(id="test")), synthetic_labeled_dataset(), tau=0.5
    )


def test_confusion_matrix_math():
    cm = confusion([True, True, False, False], [True, False, True, False])
    assert (cm.tp, cm.fn, cm.fp, cm.tn) == (1, 1, 1, 1)
    assert cm.precision == 0.5 and cm.recall == 0.5
    assert cm.fpr == 0.5 and cm.fnr == 0.5


def test_controlplane_beats_both_baselines():
    r = _report()
    for axis in [Axis.PERFORMANCE, Axis.RESPONSIBILITY]:
        cp = r.controlplane[axis]
        none = r.baselines["no_oversight"][axis]
        every = r.baselines["flag_everything"][axis]
        assert cp.recall > none.recall  # catches more than doing nothing
        assert cp.fpr < every.fpr  # fewer false alarms than flagging everything
        assert cp.f1 > none.f1 and cp.f1 > every.f1  # best F1 of the three


def test_eval_is_self_funding_and_low_latency():
    r = _report()
    assert r.cost["net_usd"] < 0.0
    assert r.cost["pct_cleared_at_t0"] >= 90.0
    assert r.cost["avg_added_latency_ms"] < 50.0


def test_miscalibrated_detector_is_surfaced():
    r = _report()
    assert "overconfidence" in r.detector_ece
    # The overconfidence heuristic is the least calibrated -- exactly what the feedback loop targets.
    assert r.detector_ece["overconfidence"] > r.detector_ece["regex_pii"]
