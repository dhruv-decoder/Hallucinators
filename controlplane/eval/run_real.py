"""Run the eval harness on a real public benchmark (HaluEval / RAGTruth) instead of the synthetic seed.

Usage:
    python -m controlplane.eval.run_real --dataset halueval --limit 500 [--models]

``--models`` uses the best-available detector stack (e.g. HHEM-2.1 groundedness) instead of heuristics, so you
can compare the cheap lexical check against the model-backed one on the *same* real data. Needs the optional
``datasets`` library; if it (or the download) is unavailable, it says so and exits without inventing numbers.
"""

from __future__ import annotations

import argparse
import sys

from controlplane.core.types import Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.eval.datasets_real import LOADERS
from controlplane.eval.harness import run_harness
from controlplane.eval.run import _fmt


def main() -> None:
    parser = argparse.ArgumentParser(description="ControlPlane eval on a real hallucination benchmark")
    parser.add_argument("--dataset", choices=sorted(LOADERS), default="halueval")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--models", action="store_true", help="use model-backed detectors (HHEM, etc.)")
    parser.add_argument("--tau", type=float, default=0.5)
    args = parser.parse_args()

    try:
        dataset = LOADERS[args.dataset](limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load '{args.dataset}': {exc}")
        print("Install the optional dep and retry:  pip install datasets")
        sys.exit(1)

    if not dataset:
        print(f"'{args.dataset}' returned no usable rows.")
        sys.exit(1)

    report = run_harness(
        lambda: build_engine(PolicyProfile(id=f"{args.dataset}@balanced"), use_models=args.models),
        dataset,
        tau=args.tau,
    )

    stack = "model-backed (HHEM/judge as available)" if args.models else "T0/T1 heuristics"
    print(f"ControlPlane evaluation -- {args.dataset} ({len(dataset)} examples, real public data)")
    print("=" * 78)
    print(f"detector stack: {stack}   operating threshold tau={report.tau}\n")
    print("[performance / groundedness]")
    print(f"  ControlPlane     {_fmt(report.controlplane[Axis.PERFORMANCE])}")
    print(f"  no-oversight     {_fmt(report.baselines['no_oversight'][Axis.PERFORMANCE])}")
    print(f"  flag-everything  {_fmt(report.baselines['flag_everything'][Axis.PERFORMANCE])}")
    print(f"\n  cleared at T0: {report.cost['pct_cleared_at_t0']:.0f}%   "
          f"avg added latency: {report.cost['avg_added_latency_ms']:.2f} ms")


if __name__ == "__main__":
    main()
