"""Measure detector calibration: ECE(raw) vs ECE(Platt-calibrated) on a held-out split.

This is the evidence for the live-calibration path (``cascade/calibrate_live.py``): fit a Platt calibrator per
detector on a train split, then report Expected Calibration Error on the *test* split, before and after. On a
substantial labelled set (HaluEval) this shows the calibration genuinely lowers ECE; on the tiny synthetic seed
it is shown only to illustrate the pipeline (too few points to trust).

    python -m controlplane.eval.run_calibration --dataset halueval --limit 600
    python -m controlplane.eval.run_calibration            # synthetic seed (illustrative)
"""

from __future__ import annotations

import argparse

import numpy as np

from controlplane.cascade.calibrate_live import collect_scores
from controlplane.cascade.calibration import PlattCalibrator, expected_calibration_error
from controlplane.eval.dataset import synthetic_labeled_dataset


def calibration_rows(dataset, split: float = 0.5, min_points: int = 30, seed: int = 0):
    """Per detector: (name, n, ece_raw_test, ece_calibrated_test) on a shuffled train/test split."""
    rng = np.random.default_rng(seed)
    rows = []
    for name, (scores, labels) in sorted(collect_scores(dataset).items()):
        x = np.asarray(scores, dtype=float)
        y = np.asarray(labels, dtype=float)
        if len(y) < min_points or y.sum() == 0 or y.sum() == len(y):
            continue
        perm = rng.permutation(len(y))
        cut = int(len(y) * split)
        tr, te = perm[:cut], perm[cut:]
        if y[tr].sum() in (0, len(tr)) or len(te) == 0:
            continue
        cal = PlattCalibrator().fit(x[tr], y[tr])
        rows.append((name, len(y),
                     expected_calibration_error(x[te], y[te]),
                     expected_calibration_error(cal.predict(x[te]), y[te])))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Detector calibration report (ECE raw vs calibrated)")
    parser.add_argument("--dataset", default="synthetic", choices=["synthetic", "halueval", "ragtruth"])
    parser.add_argument("--limit", type=int, default=600)
    args = parser.parse_args()

    if args.dataset == "synthetic":
        dataset = synthetic_labeled_dataset()
    else:
        from controlplane.eval.datasets_real import LOADERS
        dataset = LOADERS[args.dataset](limit=args.limit)

    rows = calibration_rows(dataset)
    print(f"Calibration report — {args.dataset} ({len(dataset)} examples), Platt fit on train, ECE on test")
    print("=" * 72)
    if not rows:
        print("  (no detector had enough labelled signal to calibrate — try a larger --dataset/--limit)")
        return
    print(f"  {'detector':24s} {'n':>5s} {'ECE raw':>9s} {'ECE calib':>10s} {'Δ':>8s}")
    for name, n, raw, cal in rows:
        print(f"  {name:24s} {n:5d} {raw:9.3f} {cal:10.3f} {raw - cal:+8.3f}")
    print("\n(Δ>0 means calibration lowered ECE on held-out data. Live scoring uses these fitted calibrators")
    print(" only when the labelled set is large enough; the demo seed falls back to identity — see reality guide.)")


if __name__ == "__main__":
    main()
