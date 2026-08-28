"""Fit empirical detector informativeness eta on HaluEval with a leakage-safe source split.

Example:
  python -m controlplane.eval.run_eta --limit 1000 --output artifacts/informativeness.json

The HHEM detector is force-run on the eta-fit partition. A 60/20/20 source-level split is used for calibration,
eta fitting and holdout ablation so paired correct/hallucinated HaluEval rows never cross partitions.
"""

from __future__ import annotations

import argparse
import sys

from controlplane.cascade.calibrate_live import fit_live_calibrators
from controlplane.cascade.calibration import PlattCalibrator
from controlplane.cascade.detectors.factory import build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.cascade.informativeness import EtaEstimate, bootstrap_ci, estimate_eta, save_artifact
from controlplane.core.types import Axis, PolicyProfile
from controlplane.eval.datasets_real import load_halueval_qa
from controlplane.eval.metrics import confusion
from controlplane.eval.splits import grouped_split


def _hhem_calibrator(dataset):
    import numpy as np
    detectors = build_failure_detectors(use_hhem=True, use_presidio=False, use_judge=False)
    engine = CascadeEngine(detectors, policy=PolicyProfile(id="eta-hhem-cal"), always_run=True)
    scores: list[float] = []
    labels: list[float] = []
    for ex in dataset:
        result = engine.run(ex.ctx)
        for sig in result.signals:
            if sig.name == "hhem_groundedness":
                scores.append(sig.score)
                labels.append(float(ex.labels.get(Axis.PERFORMANCE, False)))
    if len(scores) < 40 or min(labels, default=0.0) == max(labels, default=0.0):
        return None
    cal = PlattCalibrator().fit(np.asarray(scores), np.asarray(labels))
    return cal


def _run_points(dataset, calibrators, *, eta: float | None = None):
    from controlplane.core.types import PolicyProfile

    detectors = build_failure_detectors(use_hhem=True, use_presidio=False, use_judge=False)
    hhem = next((d for d in detectors if d.name == "hhem_groundedness"), None)
    if hhem is None:
        raise RuntimeError("HHEM is not available; install the [ml] extra and retry")
    if eta is not None:
        hhem.informativeness = eta
    engine = CascadeEngine(detectors, policy=PolicyProfile(id="eta-fit"), calibrators=calibrators, always_run=True)
    baseline_engine = CascadeEngine(
        build_failure_detectors(use_hhem=False, use_presidio=False, use_judge=False),
        policy=PolicyProfile(id="eta-baseline"),
        calibrators=calibrators,
    )
    rows: list[tuple[float, float, bool]] = []
    for ex in dataset:
        baseline = baseline_engine.run(ex.ctx)
        full = engine.run(ex.ctx)
        before = baseline.per_axis.get(Axis.PERFORMANCE).p_fail if Axis.PERFORMANCE in baseline.per_axis else 0.0
        after = full.per_axis.get(Axis.PERFORMANCE).p_fail if Axis.PERFORMANCE in full.per_axis else before
        rows.append((before, after, bool(ex.labels.get(Axis.PERFORMANCE, False))))
    return rows


def _holdout_metrics(dataset, calibrators, *, eta: float):
    detectors = build_failure_detectors(use_hhem=True, use_presidio=False, use_judge=False)
    hhem = next(d for d in detectors if d.name == "hhem_groundedness")
    hhem.informativeness = eta
    engine = CascadeEngine(detectors, policy=PolicyProfile(id="eta-holdout"), calibrators=calibrators)
    truth: list[bool] = []
    pred: list[bool] = []
    checks = 0
    for ex in dataset:
        result = engine.run(ex.ctx)
        truth.append(bool(ex.labels.get(Axis.PERFORMANCE, False)))
        out = result.per_axis.get(Axis.PERFORMANCE)
        pred.append(bool(out and out.p_fail >= 0.5))
        checks += sum(1 for s in result.trace if s.detector == "hhem_groundedness" and s.ran)
    cm = confusion(truth, pred)
    return {"hhem_checks": checks, "precision": cm.precision, "recall": cm.recall, "f1": cm.f1, "n": len(dataset)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", default="artifacts/informativeness.json")
    parser.add_argument("--min-samples", type=int, default=100)
    args = parser.parse_args()

    try:
        dataset = load_halueval_qa(limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load HaluEval: {exc}")
        print("Install the optional eval dependency: pip install -e '.[eval]'")
        sys.exit(1)
    if len(dataset) < 20:
        print("Need more labelled examples for eta fitting.")
        sys.exit(1)

    calibration_set, eta_set, holdout = grouped_split(dataset)
    calibrators = fit_live_calibrators(calibration_set, min_points=40)
    hhem_cal = _hhem_calibrator(calibration_set)
    if hhem_cal is None:
        print("Could not fit HHEM calibration on the calibration split; no artifact written.")
        sys.exit(1)
    calibrators = {**calibrators, "hhem_groundedness": hhem_cal}

    # Force HHEM on the eta set. The detector's manual prior is only a fallback; it is not used to select rows.
    rows = _run_points(eta_set, calibrators)
    estimate = estimate_eta(rows, prior=0.8, min_samples=args.min_samples)
    ci = bootstrap_ci(rows)
    estimate = EtaEstimate(
        detector="hhem_groundedness", prior=estimate.prior, eta=estimate.eta, n_samples=estimate.n_samples,
        numerator=estimate.numerator, denominator=estimate.denominator, source="HaluEval QA",
        split="20% eta-fit partition", min_samples=estimate.min_samples, fallback=estimate.fallback,
        bootstrap_low=ci[0] if ci else None, bootstrap_high=ci[1] if ci else None,
    )

    holdout_metrics = _holdout_metrics(holdout, calibrators, eta=estimate.eta)
    manual_metrics = _holdout_metrics(holdout, calibrators, eta=estimate.prior)
    save_artifact(args.output, {"hhem_groundedness": estimate}, dataset="HaluEval QA", fit_split="20%", holdout_split="20%")

    print("Empirical detector informativeness")
    print(f"  detector: HHEM groundedness")
    print(f"  manual eta: {estimate.prior:.3f}")
    print(f"  fitted eta: {estimate.eta:.3f}")
    print(f"  informative samples: {estimate.n_samples}")
    if ci:
        print(f"  bootstrap 95% CI: [{ci[0]:.3f}, {ci[1]:.3f}]")
    print(f"  holdout manual:  HHEM checks={manual_metrics['hhem_checks']} F1={manual_metrics['f1']:.3f} recall={manual_metrics['recall']:.3f}")
    print(f"  holdout learned: HHEM checks={holdout_metrics['hhem_checks']} F1={holdout_metrics['f1']:.3f} recall={holdout_metrics['recall']:.3f}")
    print(f"  artifact: {args.output}")


if __name__ == "__main__":
    main()
