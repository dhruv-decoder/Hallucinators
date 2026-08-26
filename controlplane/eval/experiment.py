"""The baseline experiment: no-oversight vs fixed-check vs ControlPlane, on one labelled workload.

This is the argument for *adaptive* oversight. Three conditions run over the **same** examples, same detectors,
same threshold -- only the oversight policy changes:

- **no_oversight** -- forward everything; catch nothing (recall 0, cost 0, latency 0).
- **fixed_checks** -- run *every* detector on *every* response (the obvious "just run all the guardrails"
  approach): maximum safety, maximum cost/latency.
- **controlplane** -- the VoI cascade: run the cheap checks always, buy an expensive check only when its
  information is worth more than its cost.

The intended, honest result: ControlPlane approaches fixed-check safety while running far fewer expensive
checks (lower cost/latency). We report the numbers the experiment actually produces -- if they don't support
the story, they don't.
"""

from __future__ import annotations

from controlplane.cascade.detectors.factory import build_cost_detectors, build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile
from controlplane.eval.dataset import LabeledExample
from controlplane.eval.metrics import ConfusionMatrix, confusion

_AXES = (Axis.PERFORMANCE, Axis.RESPONSIBILITY)


def _engine(always_run: bool, use_models: bool = False) -> CascadeEngine:
    # ``use_models`` adds the model tier (HHEM at T1) so there is an *expensive* check for the VoI rule to gate;
    # without it, every detector is a free T0 heuristic and the three conditions are indistinguishable.
    # HHEM only (local, no rate limit); the judge is excluded so a fixed-check run doesn't hammer a rate-limited
    # API on every example. HHEM is the expensive (T1, ~150 ms) check the VoI rule gates.
    return CascadeEngine(
        build_failure_detectors(use_hhem=use_models, use_presidio=False, use_judge=False),
        build_cost_detectors(),
        policy=PolicyProfile(id="experiment@balanced"),
        always_run=always_run,
    )


def run_experiment(dataset: list[LabeledExample], tau: float = 0.5, use_models: bool = False) -> dict:
    """Run the three conditions and return per-condition safety confusion + cost/latency/checks."""
    conditions: list[tuple[str, str | bool]] = [
        ("no_oversight", "none"), ("fixed_checks", True), ("controlplane", False),
    ]
    out: dict[str, dict] = {}
    for name, mode in conditions:
        engine = None if mode == "none" else _engine(bool(mode), use_models=use_models)
        y_true = {a: [] for a in _AXES}
        y_pred = {a: [] for a in _AXES}
        safety_spend = added_latency = 0.0
        checks_run = checks_skipped = 0
        for ex in dataset:
            for a in _AXES:
                y_true[a].append(bool(ex.labels.get(a, False)))
            if engine is None:
                for a in _AXES:
                    y_pred[a].append(False)
                continue
            res = engine.run(ex.ctx)
            for a in _AXES:
                o = res.per_axis.get(a)
                y_pred[a].append((o.p_fail if o else 0.0) >= tau)
            safety_spend += sum(s.cost_usd for s in res.signals)
            added_latency += sum(s.latency_ms for s in res.signals)
            for step in res.trace:
                if int(step.tier) > 0:
                    checks_run += int(step.ran)
                    checks_skipped += int(not step.ran)
        out[name] = {
            "confusion": {a.value: confusion(y_true[a], y_pred[a]) for a in _AXES},
            "safety_spend_usd": round(safety_spend, 5),
            "added_latency_ms": round(added_latency, 2),
            "expensive_checks_run": checks_run,
            "expensive_checks_skipped": checks_skipped,
            "n": len(dataset),
        }
    return out


def macro_recall(cm: dict[str, ConfusionMatrix]) -> float:
    """Average failure-detection recall over axes that actually have failures (empty axes would dilute it)."""
    vals = [c.recall for c in cm.values() if (c.tp + c.fn) > 0]
    return sum(vals) / len(vals) if vals else 0.0
