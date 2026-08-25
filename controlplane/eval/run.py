"""CLI for the reproducible ControlPlane evaluation."""

from __future__ import annotations

import argparse

from controlplane.core.types import Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.harness import EvalReport, run_harness
from controlplane.eval.metrics import ConfusionMatrix


def _fmt(cm: ConfusionMatrix) -> str:
    return (
        f"P={cm.precision:.2f} R={cm.recall:.2f} F1={cm.f1:.2f} "
        f"FPR={cm.fpr:.2f} FNR={cm.fnr:.2f}"
    )


def print_report(report: EvalReport) -> None:
    print("ControlPlane evaluation -- reproducible labelled seed")
    print("=" * 88)
    print(f"n={report.n} examples, tau={report.tau}")
    for axis in (Axis.PERFORMANCE, Axis.RESPONSIBILITY):
        print(f"\n[{axis.value}]")
        print(f"  ControlPlane   {_fmt(report.controlplane[axis])}")
        print(f"  Verify-all     {_fmt(report.baselines['verify_all'][axis])}")
        print(f"  Verify-none    {_fmt(report.baselines['verify_none'][axis])}")
    c = report.cost
    print("\nLatency / cost")
    print(f"  ControlPlane p50={c['p50_added_latency_ms']:.2f} ms p95={c['p95_added_latency_ms']:.2f} ms")
    print(f"  cleared at T0={c['pct_cleared_at_t0']:.1f}%")
    print(f"  safety spend=${c['safety_spend_usd']:.4f} saved=${c['cost_saved_usd']:.4f} net=${c['net_usd']:+.4f}")
    print(f"  verify-all safety spend=${c['verify_all_safety_spend_usd']:.4f}")
    print("\nECE")
    for name, ece in sorted(report.detector_ece.items()):
        print(f"  {name:24s} ECE={ece:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="artifacts/eval_report.json")
    args = parser.parse_args()
    dataset = synthetic_labeled_dataset()
    report = run_harness(lambda: build_engine(PolicyProfile(id="eval@balanced")), dataset, tau=0.5, json_path=args.json)
    print_report(report)


if __name__ == "__main__":
    main()
