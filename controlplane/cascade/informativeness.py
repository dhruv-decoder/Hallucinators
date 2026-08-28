"""Offline empirical estimation of detector informativeness eta.

Eta is the fraction of the perfect-information decision-value gain delivered by a detector. The estimator is
run offline on forced-check labelled data to avoid learning only from checks selected by the current VoI rule.
Artifacts carry source/split metadata and a manual prior fallback; runtime never depends on the artifact being
present or valid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class EtaEstimate:
    detector: str
    prior: float
    eta: float
    n_samples: int
    numerator: float
    denominator: float
    method: str = "decision_value_gain_ratio"
    source: str = "unknown"
    split: str = "unknown"
    min_samples: int = 100
    fallback: bool = False
    bootstrap_low: float | None = None
    bootstrap_high: float | None = None


def _row_eta(
    p_before: float, p_after: float, failure: bool, cost_fail: float, cost_mitigate: float
) -> tuple[float, float]:
    before = min(max(p_before, 0.0), 1.0) * cost_fail
    before = min(before, cost_mitigate)
    after = min(max(p_after, 0.0), 1.0) * cost_fail
    after = min(after, cost_mitigate)
    perfect = min(cost_fail, cost_mitigate) if failure else 0.0
    return before - after, max(before - perfect, 0.0)


def estimate_eta(
    rows: list[tuple[float, float, bool]],
    *,
    prior: float,
    min_samples: int = 100,
    cost_fail: float = 1.0,
    cost_mitigate: float = 0.05,
) -> EtaEstimate:
    """Estimate eta from forced detector outcomes using realized/available decision-value gain."""
    numerator = 0.0
    denominator = 0.0
    used = 0
    for p_before, p_after, failure in rows:
        gain, available = _row_eta(p_before, p_after, failure, cost_fail, cost_mitigate)
        if available <= 1e-12:
            continue
        numerator += gain
        denominator += available
        used += 1
    if used < min_samples or denominator <= 1e-12:
        return EtaEstimate(
            "", prior, max(0.0, min(1.0, prior)), used, numerator, denominator,
            min_samples=min_samples, fallback=True,
        )
    eta = max(0.0, min(1.0, numerator / denominator))
    return EtaEstimate("", prior, eta, used, numerator, denominator, min_samples=min_samples)


def bootstrap_ci(
    rows: list[tuple[float, float, bool]], *, seed: int = 0, n_boot: int = 1000, alpha: float = 0.05,
    cost_fail: float = 1.0, cost_mitigate: float = 0.05,
) -> tuple[float, float] | None:
    """Bootstrap a CI for eta; returns None when fewer than 2 informative rows exist."""
    informative = [r for r in rows if _row_eta(*r, cost_fail, cost_mitigate)[1] > 1e-12]
    if len(informative) < 2:
        return None
    import numpy as np

    rng = np.random.default_rng(seed)
    arr = np.asarray(informative, dtype=object)
    vals: list[float] = []
    for _ in range(n_boot):
        sample = arr[rng.integers(0, len(arr), size=len(arr))]
        num = den = 0.0
        for p_before, p_after, failure in sample.tolist():
            gain, available = _row_eta(float(p_before), float(p_after), bool(failure), cost_fail, cost_mitigate)
            num += gain
            den += available
        vals.append(max(0.0, min(1.0, num / den)) if den > 0 else 0.0)
    return tuple(float(x) for x in np.quantile(vals, [alpha / 2, 1 - alpha / 2]))


def save_artifact(
    path: str | Path, estimates: dict[str, EtaEstimate], *, dataset: str, fit_split: str, holdout_split: str
) -> None:
    payload = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "method": "decision_value_gain_ratio",
        "dataset": dataset,
        "fit_split": fit_split,
        "holdout_split": holdout_split,
        "estimates": {
            name: {
                "prior": e.prior,
                "eta": e.eta,
                "n_samples": e.n_samples,
                "numerator": e.numerator,
                "denominator": e.denominator,
                "source": e.source,
                "split": e.split,
                "min_samples": e.min_samples,
                "fallback": e.fallback,
                "bootstrap_low": e.bootstrap_low,
                "bootstrap_high": e.bootstrap_high,
            }
            for name, e in estimates.items()
        },
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_artifact(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        estimates = data.get("estimates", {})
        return estimates if isinstance(estimates, dict) else {}
    except Exception:  # noqa: BLE001 - invalid artifacts must never break runtime
        return {}


def apply_artifact(detectors, estimates: dict[str, dict]) -> dict[str, float]:
    """Apply only validated eta values to detector instances and return the values actually applied."""
    applied: dict[str, float] = {}
    for detector in detectors:
        item = estimates.get(detector.name)
        if not isinstance(item, dict) or item.get("fallback"):
            continue
        try:
            eta = float(item["eta"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.0 <= eta <= 1.0:
            detector.informativeness = eta
            applied[detector.name] = eta
    return applied
