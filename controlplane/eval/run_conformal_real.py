"""Build a conformal escaped-failure certificate from real public labelled data.

Example:
  python -m controlplane.eval.run_conformal_real --dataset halueval --limit 1000 --output artifacts/conformal_performance.json

The certificate is fitted on a held-out calibration partition. It is a finite-sample expected conditional-FNR
certificate for future failures that are exchangeable with the calibration failures; it is not a 1-alpha
probability confidence statement and it does not certify distribution shift.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from controlplane.cascade.conformal import risk_controlled_threshold
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine
from controlplane.eval.datasets_real import LOADERS
from controlplane.eval.splits import grouped_split


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=sorted(LOADERS), default="halueval")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", default="artifacts/conformal_performance.json")
    parser.add_argument("--models", action="store_true", help="use HHEM when available; otherwise heuristics-only")
    args = parser.parse_args()

    try:
        dataset = LOADERS[args.dataset](limit=args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load '{args.dataset}': {exc}")
        print("Install the optional eval dependency: pip install -e '.[eval]'")
        sys.exit(1)
    if len(dataset) < 20:
        print("Need more labelled examples for conformal calibration.")
        sys.exit(1)

    _, calibration_set, holdout = grouped_split(dataset)
    engine = build_engine(PolicyProfile(id=f"conformal@{args.dataset}"), use_models=args.models)
    scores: list[float] = []
    labels: list[bool] = []
    for ex in calibration_set:
        result = engine.run(ex.ctx)
        outcome = result.per_axis.get(Axis.PERFORMANCE)
        scores.append(outcome.p_fail if outcome else 0.0)
        labels.append(bool(ex.labels.get(Axis.PERFORMANCE, False)))

    certs = []
    for alpha in (0.20, 0.10, 0.05):
        c = risk_controlled_threshold(scores, labels, alpha)
        certs.append({
            "alpha": alpha,
            "valid": c.valid,
            "tau": round(c.tau, 6),
            "empirical_fnr": round(c.empirical_fnr, 6),
            "risk_bound": round(c.risk_bound, 6),
            "n_failures": c.n_failures,
            "statement": c.statement(),
        })

    # Holdout is deliberately not used to choose tau. Report a simple descriptive escaped-failure rate at each
    # certified threshold so the artifact can show calibration vs held-out behavior without leaking into fitting.
    holdout_scores: list[float] = []
    holdout_labels: list[bool] = []
    for ex in holdout:
        result = engine.run(ex.ctx)
        outcome = result.per_axis.get(Axis.PERFORMANCE)
        holdout_scores.append(outcome.p_fail if outcome else 0.0)
        holdout_labels.append(bool(ex.labels.get(Axis.PERFORMANCE, False)))
    for item in certs:
        if item["valid"]:
            failures = [s for s, y in zip(holdout_scores, holdout_labels, strict=True) if y]
            item["holdout_fnr"] = round(sum(s < item["tau"] for s in failures) / len(failures), 6) if failures else None
        else:
            item["holdout_fnr"] = None

    payload = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "axis": "performance",
        "source": f"real_public_{args.dataset}",
        "score_source": "model-backed" if args.models else "heuristics-only",
        "calibration_split": "20% source-grouped partition",
        "holdout_split": "20% source-grouped partition (descriptive only)",
        "risk_definition": "P(pass | true failure)",
        "assumption": "future failure examples are exchangeable with calibration failures",
        "certificates": certs,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out}")
    for item in certs:
        print(f"alpha={item['alpha']:.2f} valid={item['valid']} tau={item['tau']:.3f} bound={item['risk_bound']:.3f} holdout_fnr={item['holdout_fnr']}")


if __name__ == "__main__":
    main()
