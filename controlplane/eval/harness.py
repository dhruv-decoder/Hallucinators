"""Evaluation harness for ControlPlane and two reference baselines.

The benchmark deliberately keeps the policy/detector code unchanged: the harness is a thin runner that
measures the same labelled workload under (1) the live VoI cascade, (2) verify-none, and (3) verify-all.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from controlplane.cascade.calibration import expected_calibration_error
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis
from controlplane.eval.dataset import LabeledExample
from controlplane.eval.metrics import ConfusionMatrix, confusion, percentile
from controlplane.pnl import PnlLedger

_FAILURE_AXES = (Axis.PERFORMANCE, Axis.RESPONSIBILITY)


@dataclass
class StrategyReport:
    """Metrics produced for one evaluation strategy."""

    confusion: dict[Axis, ConfusionMatrix] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    safety_spend_usd: float = 0.0
    cost_saved_usd: float = 0.0
    net_usd: float = 0.0
    pct_cleared_at_t0: float = 0.0


@dataclass
class EvalReport:
    """Everything the harness measured on one dataset."""

    n: int
    tau: float
    controlplane: dict[Axis, ConfusionMatrix] = field(default_factory=dict)
    baselines: dict[str, dict[Axis, ConfusionMatrix]] = field(default_factory=dict)
    cost: dict[str, float] = field(default_factory=dict)
    detector_ece: dict[str, float] = field(default_factory=dict)
    strategies: dict[str, StrategyReport] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "tau": self.tau,
            "strategies": {
                name: {
                    "confusion": {axis.value: vars(cm) for axis, cm in rep.confusion.items()},
                    "avg_latency_ms": rep.avg_latency_ms,
                    "p50_latency_ms": rep.p50_latency_ms,
                    "p95_latency_ms": rep.p95_latency_ms,
                    "p99_latency_ms": rep.p99_latency_ms,
                    "safety_spend_usd": rep.safety_spend_usd,
                    "cost_saved_usd": rep.cost_saved_usd,
                    "net_usd": rep.net_usd,
                    "pct_cleared_at_t0": rep.pct_cleared_at_t0,
                }
                for name, rep in self.strategies.items()
            },
            "detector_ece": self.detector_ece,
        }


def _strategy_metrics(
    dataset: list[LabeledExample], results, tau: float, *, ledger: PnlLedger
) -> StrategyReport:
    y_true = {a: [] for a in _FAILURE_AXES}
    y_pred = {a: [] for a in _FAILURE_AXES}
    latencies: list[float] = []
    t0 = 0
    for example, result, elapsed_ms in results:
        latencies.append(elapsed_ms)
        for axis in _FAILURE_AXES:
            truth = bool(example.labels.get(axis, False))
            p_fail = result.per_axis[axis].p_fail if axis in result.per_axis else 0.0
            y_true[axis].append(truth)
            y_pred[axis].append(p_fail >= tau)
        if not any(step.ran and step.tier > 0 for step in result.trace):
            t0 += 1
    totals = ledger.totals()
    return StrategyReport(
        confusion={a: confusion(y_true[a], y_pred[a]) for a in _FAILURE_AXES},
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        p50_latency_ms=percentile(latencies, 50),
        p95_latency_ms=percentile(latencies, 95),
        p99_latency_ms=percentile(latencies, 99),
        safety_spend_usd=totals.safety_spend_usd,
        cost_saved_usd=totals.cost_saved_usd,
        net_usd=totals.net_usd,
        pct_cleared_at_t0=100.0 * t0 / len(dataset) if dataset else 0.0,
    )


def run_harness(
    engine_factory: Callable[[], CascadeEngine],
    dataset: list[LabeledExample],
    tau: float = 0.5,
    *,
    json_path: str | Path | None = None,
) -> EvalReport:
    control_engine = engine_factory()
    verify_all_engine = engine_factory()
    control_results = []
    all_results = []
    control_ledger = PnlLedger()
    all_ledger = PnlLedger()
    det_scores: dict[str, list[float]] = {}
    det_labels: dict[str, list[float]] = {}

    for example in dataset:
        start = time.perf_counter()
        result = control_engine.run(example.ctx)
        elapsed = (time.perf_counter() - start) * 1000.0
        control_ledger.book(example.ctx, result)
        control_results.append((example, result, elapsed))
        for sig in result.signals:
            label = 1.0 if example.labels.get(sig.axis, False) else 0.0
            det_scores.setdefault(sig.name, []).append(sig.score)
            det_labels.setdefault(sig.name, []).append(label)

        start = time.perf_counter()
        all_result = verify_all_engine.run_all(example.ctx)
        all_elapsed = (time.perf_counter() - start) * 1000.0
        all_ledger.book(example.ctx, all_result)
        all_results.append((example, all_result, all_elapsed))

    control_report = _strategy_metrics(dataset, control_results, tau, ledger=control_ledger)
    verify_all_report = _strategy_metrics(dataset, all_results, tau, ledger=all_ledger)

    no_oversight_cm = {
        axis: confusion(
            [bool(example.labels.get(axis, False)) for example in dataset],
            [False] * len(dataset),
        )
        for axis in _FAILURE_AXES
    }
    flag_all_cm = {
        axis: confusion(
            [bool(example.labels.get(axis, False)) for example in dataset],
            [True] * len(dataset),
        )
        for axis in _FAILURE_AXES
    }

    report = EvalReport(
        n=len(dataset),
        tau=tau,
        controlplane=control_report.confusion,
        baselines={
            "verify_none": no_oversight_cm,
            "verify_all": verify_all_report.confusion,
            "no_oversight": no_oversight_cm,
            "flag_everything": flag_all_cm,
        },
        cost={
            "cost_saved_usd": control_report.cost_saved_usd,
            "safety_spend_usd": control_report.safety_spend_usd,
            "net_usd": control_report.net_usd,
            "pct_cleared_at_t0": control_report.pct_cleared_at_t0,
            "avg_added_latency_ms": control_report.avg_latency_ms,
            "p50_added_latency_ms": control_report.p50_latency_ms,
            "p95_added_latency_ms": control_report.p95_latency_ms,
            "p99_added_latency_ms": control_report.p99_latency_ms,
            "verify_all_safety_spend_usd": verify_all_report.safety_spend_usd,
        },
        detector_ece={
            name: expected_calibration_error(np.array(det_scores[name]), np.array(det_labels[name]))
            for name in det_scores
        },
        strategies={"controlplane": control_report, "verify_all": verify_all_report},
    )
    if json_path:
        out = Path(json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return report
