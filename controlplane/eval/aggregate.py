"""Leakage-aware aggregate evaluation on public labelled data.

The benchmark separates model warm-up from measured cascade latency and compares the same labelled examples
under no oversight, fixed checks, and the adaptive ControlPlane cascade. Confusion metrics are computed once
per example; latency statistics use independent repeated passes over the same examples.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from controlplane.cascade.detectors.factory import build_cost_detectors, build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile
from controlplane.eval.dataset import LabeledExample
from controlplane.eval.datasets_real import LOADERS
from controlplane.eval.metrics import bootstrap_f1_ci, confusion

_AXES = (Axis.PERFORMANCE, Axis.RESPONSIBILITY)


@dataclass
class AggregateStrategy:
    name: str
    n: int
    errors: int
    latency_ms: dict[str, float]
    confusion: dict[str, dict[str, float | int]]
    expensive_checks_run: int
    expensive_checks_skipped: int
    t0_clearance_pct: float


def _cm_dict(cm) -> dict:
    return {
        "tp": cm.tp, "fp": cm.fp, "fn": cm.fn, "tn": cm.tn,
        "precision": round(cm.precision, 4), "recall": round(cm.recall, 4),
        "f1": round(cm.f1, 4), "fpr": round(cm.fpr, 4), "fnr": round(cm.fnr, 4),
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    rank = (p / 100.0) * (len(xs) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    return float(xs[lo] + (xs[hi] - xs[lo]) * (rank - lo))


def _run_once(
    engine: CascadeEngine,
    dataset: list[LabeledExample],
    tau: float,
    *,
    measure_latency: bool,
) -> tuple[list[float], dict[Axis, list[bool]], dict[Axis, list[bool]], int, int, int, int]:
    latencies: list[float] = []
    y_true = {a: [] for a in _AXES}
    y_pred = {a: [] for a in _AXES}
    checks_run = checks_skipped = t0 = errors = 0

    for ex in dataset:
        try:
            started = time.perf_counter()
            result = engine.run(ex.ctx)
            if measure_latency:
                latencies.append((time.perf_counter() - started) * 1000.0)
            for axis in _AXES:
                y_true[axis].append(bool(ex.labels.get(axis, False)))
                outcome = result.per_axis.get(axis)
                y_pred[axis].append((outcome.p_fail if outcome else 0.0) >= tau)
            if not any(step.ran and int(step.tier) > 0 for step in result.trace):
                t0 += 1
            for step in result.trace:
                if int(step.tier) > 0:
                    checks_run += int(step.ran)
                    checks_skipped += int(not step.ran)
        except Exception:
            errors += 1

    return latencies, y_true, y_pred, checks_run, checks_skipped, t0, errors


def _strategy_from_runs(
    name: str,
    dataset: list[LabeledExample],
    tau: float,
    engine: CascadeEngine,
    *,
    warmup: int,
    repeats: int,
) -> AggregateStrategy:
    # Warm-up uses the exact detector stack and is excluded from all reported latency samples.
    if warmup > 0:
        for ex in dataset[: min(warmup, len(dataset))]:
            try:
                engine.run(ex.ctx)
            except Exception:
                pass

    # First measured pass supplies the labelled confusion metrics and trace counts.
    first_lat, y_true, y_pred, checks_run, checks_skipped, t0, errors = _run_once(
        engine, dataset, tau, measure_latency=True
    )
    all_latencies = list(first_lat)

    # Repeated passes are only used to stabilize latency percentiles; don't duplicate labelled n/confusion.
    for _ in range(max(0, repeats - 1)):
        lat, _, _, _, _, _, err = _run_once(engine, dataset, tau, measure_latency=True)
        all_latencies.extend(lat)
        errors += err

    confusion_map = {}
    for axis in _AXES:
        cm = confusion(y_true[axis], y_pred[axis])
        f1_lo, f1_hi = bootstrap_f1_ci(y_true[axis], y_pred[axis], n_boot=1000)
        c = _cm_dict(cm)
        c["f1_ci_low"] = round(f1_lo, 4)
        c["f1_ci_high"] = round(f1_hi, 4)
        confusion_map[axis.value] = c

    return AggregateStrategy(
        name=name,
        n=len(dataset),
        errors=errors,
        latency_ms={
            "p50": round(_percentile(all_latencies, 50), 3),
            "p95": round(_percentile(all_latencies, 95), 3),
            "p99": round(_percentile(all_latencies, 99), 3),
            "mean": round(float(np.mean(all_latencies)) if all_latencies else 0.0, 3),
            "samples": len(all_latencies),
        },
        confusion=confusion_map,
        expensive_checks_run=checks_run,
        expensive_checks_skipped=checks_skipped,
        t0_clearance_pct=round(100.0 * t0 / len(dataset), 2) if dataset else 0.0,
    )


def _baseline_from_truth(dataset: list[LabeledExample], name: str) -> AggregateStrategy:
    cms = {}
    for axis in _AXES:
        truth = [bool(ex.labels.get(axis, False)) for ex in dataset]
        pred = [False] * len(dataset) if name == "no_oversight" else [True] * len(dataset)
        cms[axis.value] = _cm_dict(confusion(truth, pred))
    return AggregateStrategy(
        name=name, n=len(dataset), errors=0,
        latency_ms={"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "samples": 0},
        confusion=cms,
        expensive_checks_run=0, expensive_checks_skipped=0,
        t0_clearance_pct=0.0,
    )


def run(
    dataset: list[LabeledExample], *, tau: float, use_models: bool, warmup: int, repeats: int
) -> dict:
    cp = _strategy_from_runs(
        "controlplane", dataset, tau, _control_engine(use_models=use_models), warmup=warmup, repeats=repeats
    )
    fixed = _strategy_from_runs(
        "fixed_checks", dataset, tau, _fixed_engine(use_models=use_models), warmup=warmup, repeats=repeats
    )
    none = _baseline_from_truth(dataset, "no_oversight")
    all_flag = _baseline_from_truth(dataset, "flag_everything")
    return {
        "methodology": {
            "n_requested": len(dataset),
            "tau": tau,
            "models": use_models,
            "warmup_samples_excluded": warmup,
            "latency_repeats": repeats,
            "same_examples": True,
            "confusion_passes": 1,
            "cold_start_excluded_from_latency": True,
            "axes": [a.value for a in _AXES],
            "note": "End-to-end model/network latency is not included; the latency columns measure local cascade execution only.",
            "fixed_checks_note": "fixed_checks uses always_run=True over the same detector stack; no_oversight and flag_everything are prediction baselines.",
        },
        "strategies": {s.name: asdict(s) for s in (none, fixed, cp, all_flag)},
    }


def _control_engine(*, use_models: bool) -> CascadeEngine:
    return CascadeEngine(
        build_failure_detectors(use_hhem=use_models, use_presidio=False, use_judge=False),
        build_cost_detectors(),
        policy=PolicyProfile(id="aggregate@balanced"),
        always_run=False,
    )


def _fixed_engine(*, use_models: bool) -> CascadeEngine:
    return CascadeEngine(
        build_failure_detectors(use_hhem=use_models, use_presidio=False, use_judge=False),
        build_cost_detectors(),
        policy=PolicyProfile(id="aggregate@fixed"),
        always_run=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate public-benchmark evaluation for ControlPlane")
    parser.add_argument("--dataset", choices=sorted(LOADERS), default="halueval")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--models", action="store_true", help="include HHEM as the gated T1 model")
    parser.add_argument("--tau", type=float, default=0.5)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", default="artifacts/aggregate_eval.json")
    args = parser.parse_args()

    if args.limit < 1 or args.warmup < 0 or args.repeats < 1 or not 0.0 <= args.tau <= 1.0:
        raise SystemExit("--limit >=1, --warmup >=0, --repeats >=1, and 0<=--tau<=1 are required")

    try:
        dataset = LOADERS[args.dataset](limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load '{args.dataset}': {exc}", file=sys.stderr)
        print("Install the optional dependency with: pip install -e '.[eval]'", file=sys.stderr)
        raise SystemExit(1) from exc

    if not dataset:
        print("No usable labelled examples were loaded.", file=sys.stderr)
        raise SystemExit(1)

    artifact = run(dataset, tau=args.tau, use_models=args.models, warmup=args.warmup, repeats=args.repeats)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    print(f"ControlPlane aggregate evaluation — {args.dataset} ({len(dataset)} examples)")
    print("=" * 110)
    print(
        f"models={'on' if args.models else 'off'}  tau={args.tau:.2f}  "
        f"warm-up excluded={args.warmup}  latency repeats={args.repeats}"
    )
    print(
        f"{'strategy':18s} {'p95 ms':>10s} {'F1 perf':>10s} {'Recall perf':>13s} "
        f"{'FPR perf':>10s} {'F1 resp':>10s} {'T0 clear':>10s} {'exp checks':>12s}"
    )
    print("-" * 110)
    for name in ("no_oversight", "flag_everything", "fixed_checks", "controlplane"):
        s = artifact["strategies"][name]
        perf, resp = s["confusion"]["performance"], s["confusion"]["responsibility"]
        print(
            f"{name:18s} {s['latency_ms']['p95']:10.3f} {perf['f1']:10.3f} {perf['recall']:13.3f} "
            f"{perf['fpr']:10.3f} {resp['f1']:10.3f} {s['t0_clearance_pct']:10.2f}% {s['expensive_checks_run']:12d}"
        )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
