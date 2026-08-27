"""Run the engine over a labelled dataset and compute detection quality, baselines, cost, calibration.

Detection metrics are per axis at an operating threshold ``tau``: a request is counted as a predicted
failure on an axis when the engine's calibrated ``p_fail`` for that axis is at least ``tau``. Two
reference baselines bracket the trade-off: "no oversight" (predict nothing -> misses every failure) and
"flag everything" (predict every failure -> maximum false positives). ControlPlane should sit far better
than both.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from controlplane.cascade.calibration import expected_calibration_error
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis
from controlplane.eval.dataset import LabeledExample
from controlplane.eval.metrics import ConfusionMatrix, confusion
from controlplane.pnl import PnlLedger

_FAILURE_AXES = (Axis.PERFORMANCE, Axis.RESPONSIBILITY)


@dataclass
class EvalReport:
    """Everything the harness measured on one dataset."""

    n: int
    tau: float
    controlplane: dict[Axis, ConfusionMatrix] = field(default_factory=dict)
    baselines: dict[str, dict[Axis, ConfusionMatrix]] = field(default_factory=dict)
    cost: dict[str, float] = field(default_factory=dict)
    detector_ece: dict[str, float] = field(default_factory=dict)
    # Raw aligned (truth, prediction) per axis for ControlPlane, so callers can bootstrap CIs on any metric.
    raw: dict[Axis, tuple[list[bool], list[bool]]] = field(default_factory=dict)


def run_harness(
    engine_factory: Callable[[], CascadeEngine],
    dataset: list[LabeledExample],
    tau: float = 0.5,
) -> EvalReport:
    engine = engine_factory()
    ledger = PnlLedger()

    y_true: dict[Axis, list[bool]] = {a: [] for a in _FAILURE_AXES}
    y_pred: dict[Axis, list[bool]] = {a: [] for a in _FAILURE_AXES}
    det_scores: dict[str, list[float]] = {}
    det_labels: dict[str, list[float]] = {}
    cleared_at_t0 = 0
    added_latency = 0.0

    for example in dataset:
        result = engine.run(example.ctx)
        ledger.book(example.ctx, result)

        for axis in _FAILURE_AXES:
            truth = bool(example.labels.get(axis, False))
            p_fail = result.per_axis[axis].p_fail if axis in result.per_axis else 0.0
            y_true[axis].append(truth)
            y_pred[axis].append(p_fail >= tau)

        for sig in result.signals:
            label = 1.0 if example.labels.get(sig.axis, False) else 0.0
            det_scores.setdefault(sig.name, []).append(sig.score)
            det_labels.setdefault(sig.name, []).append(label)

        if not any(step.ran and step.tier > 0 for step in result.trace):
            cleared_at_t0 += 1
        added_latency += sum(sig.latency_ms for sig in result.signals)

    n = len(dataset)
    controlplane = {a: confusion(y_true[a], y_pred[a]) for a in _FAILURE_AXES}
    baselines = {
        "no_oversight": {a: confusion(y_true[a], [False] * n) for a in _FAILURE_AXES},
        "flag_everything": {a: confusion(y_true[a], [True] * n) for a in _FAILURE_AXES},
    }
    totals = ledger.totals()
    cost = {
        "cost_saved_usd": totals.cost_saved_usd,
        "safety_spend_usd": totals.safety_spend_usd,
        "net_usd": totals.net_usd,
        "pct_cleared_at_t0": 100.0 * cleared_at_t0 / n if n else 0.0,
        "avg_added_latency_ms": added_latency / n if n else 0.0,
    }
    detector_ece = {
        name: expected_calibration_error(np.array(det_scores[name]), np.array(det_labels[name]))
        for name in det_scores
    }
    raw = {a: (y_true[a], y_pred[a]) for a in _FAILURE_AXES}
    return EvalReport(
        n=n, tau=tau, controlplane=controlplane, baselines=baselines, cost=cost,
        detector_ece=detector_ece, raw=raw,
    )
