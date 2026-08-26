"""Print the baseline vs fixed-check vs ControlPlane comparison (``make experiment``).

    python -m controlplane.eval.run_experiment                     # synthetic seed
    python -m controlplane.eval.run_experiment --dataset halueval --limit 400
"""

from __future__ import annotations

import argparse

from controlplane.core.types import Axis
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.experiment import macro_recall, run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="No-oversight vs fixed-check vs ControlPlane")
    parser.add_argument("--dataset", default="synthetic", choices=["synthetic", "halueval", "ragtruth"])
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--tau", type=float, default=0.5)
    parser.add_argument("--models", action="store_true",
                        help="add the model tier (HHEM) so there is an expensive check to gate")
    args = parser.parse_args()

    if args.dataset == "synthetic":
        dataset = synthetic_labeled_dataset()
    else:
        from controlplane.eval.datasets_real import LOADERS
        dataset = LOADERS[args.dataset](limit=args.limit)

    res = run_experiment(dataset, tau=args.tau, use_models=args.models)
    print(f"Baseline experiment — {args.dataset} ({len(dataset)} examples, tau={args.tau})")
    print("=" * 84)
    print(f"  {'condition':14s} {'recall':>7s} {'perf F1':>8s} {'resp F1':>8s} "
          f"{'safety $':>9s} {'added ms':>9s} {'checks run':>11s} {'skipped':>8s}")
    for name in ("no_oversight", "fixed_checks", "controlplane"):
        r = res[name]
        cm = r["confusion"]
        print(f"  {name:14s} {macro_recall(cm):7.2f} "
              f"{cm[Axis.PERFORMANCE.value].f1:8.2f} {cm[Axis.RESPONSIBILITY.value].f1:8.2f} "
              f"{r['safety_spend_usd']:9.4f} {r['added_latency_ms']:9.1f} "
              f"{r['expensive_checks_run']:11d} {r['expensive_checks_skipped']:8d}")

    cp, fx = res["controlplane"], res["fixed_checks"]
    saved = fx["expensive_checks_run"] - cp["expensive_checks_run"]
    print(f"\n  ControlPlane ran {cp['expensive_checks_run']} expensive checks vs fixed-check's "
          f"{fx['expensive_checks_run']} ({saved} avoided), at recall "
          f"{macro_recall(cp['confusion']):.2f} vs {macro_recall(fx['confusion']):.2f}.")
    print("  (Same workload/detectors/threshold; only the oversight policy changes. Numbers as measured.)")


if __name__ == "__main__":
    main()
