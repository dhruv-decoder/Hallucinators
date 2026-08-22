"""Run the evaluation harness on the synthetic labelled set and print the report.

Run with ``make eval`` or ``python -m controlplane.eval.run``. Every number below is regenerated here from
the labelled dataset -- nothing is hard-coded, per AI_CODING_GUIDELINES.md.
"""

from __future__ import annotations

from controlplane.core.types import Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.harness import EvalReport, run_harness
from controlplane.eval.metrics import ConfusionMatrix


def _fmt(cm: ConfusionMatrix) -> str:
    return (
        f"P={cm.precision:.2f} R={cm.recall:.2f} F1={cm.f1:.2f} "
        f"FPR={cm.fpr:.2f} FNR={cm.fnr:.2f}  (tp={cm.tp} fp={cm.fp} fn={cm.fn} tn={cm.tn})"
    )


def print_report(report: EvalReport) -> None:
    print("ControlPlane evaluation -- synthetic labelled set")
    print("=" * 78)
    print(f"n={report.n} examples, operating threshold tau={report.tau}")
    print("(Synthetic seed data for wiring the harness; P3 swaps in labelled public data.)\n")

    for axis in [Axis.PERFORMANCE, Axis.RESPONSIBILITY]:
        print(f"[{axis.value}]")
        print(f"  ControlPlane     {_fmt(report.controlplane[axis])}")
        print(f"  no-oversight     {_fmt(report.baselines['no_oversight'][axis])}")
        print(f"  flag-everything  {_fmt(report.baselines['flag_everything'][axis])}")
        print()

    c = report.cost
    print("Cost / latency")
    print(f"  cost saved ${c['cost_saved_usd']:.4f}  safety spend ${c['safety_spend_usd']:.4f}  "
          f"net ${c['net_usd']:+.4f}")
    print(f"  cleared at T0: {c['pct_cleared_at_t0']:.0f}%   avg added latency: "
          f"{c['avg_added_latency_ms']:.2f} ms\n")

    print("Detector calibration error (raw scores; the feedback loop lowers these)")
    for name, ece in sorted(report.detector_ece.items()):
        print(f"  {name:24s} ECE={ece:.3f}")


def main() -> None:
    report = run_harness(
        lambda: build_engine(PolicyProfile(id="eval@balanced")),
        synthetic_labeled_dataset(),
        tau=0.5,
    )
    print_report(report)


if __name__ == "__main__":
    main()
