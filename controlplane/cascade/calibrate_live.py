"""Fit per-detector calibrators from labelled data, for the *live* scoring path.

The engine accepts a ``{detector_name: Calibrator}`` map (``cascade/engine.py``) but the service historically
passed none, so live ``p_fail`` was the raw detector score (``IdentityCalibrator``). This module closes that
gap: it runs the heuristic detectors over a labelled set, pairs each detector's raw score with the ground-truth
label *for that detector's axis*, and fits a **Platt** calibrator (robust on small data) per detector. The
service loads these at startup, so the VoI arithmetic uses calibrated probabilities.

Honest scope: the bundled seed is tiny (18 examples), so a detector is only calibrated when it has enough
signal (both classes, >= ``min_points``); otherwise it falls back to identity. Production would fit on a large
held-out labelled split; here it is a real wiring of the calibration path with a safe fallback, and the eval
reports the ECE before/after so the effect is measured, not asserted.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from controlplane.cascade.calibration import Calibrator, PlattCalibrator
from controlplane.cascade.detectors.factory import build_cost_detectors, build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import PolicyProfile
from controlplane.eval.dataset import LabeledExample


def collect_scores(dataset: list[LabeledExample]) -> dict[str, tuple[list[float], list[int]]]:
    """Run the heuristic detectors over the dataset and gather ``(raw_score, axis_label)`` per detector."""
    engine = CascadeEngine(
        build_failure_detectors(use_hhem=False, use_presidio=False, use_judge=False),
        build_cost_detectors(),
        policy=PolicyProfile(id="calib"),
    )
    per_detector: dict[str, tuple[list[float], list[int]]] = {}
    for ex in dataset:
        result = engine.run(ex.ctx)
        for sig in result.signals:
            label = bool(ex.labels.get(sig.axis, False))
            scores, labels = per_detector.setdefault(sig.name, ([], []))
            scores.append(sig.score)
            labels.append(int(label))
    return per_detector


def fit_live_calibrators(
    dataset: list[LabeledExample], min_points: int = 40
) -> dict[str, Calibrator]:
    """Fit a Platt calibrator per detector with enough labelled signal; skip the rest (engine uses identity).

    ``min_points`` is deliberately high: calibrating on a tiny set (e.g. the 18-example seed) distorts more
    than it helps and would move the carefully-tuned demo actions, so the seed correctly falls back to identity.
    Calibration only activates on a substantial labelled set (e.g. HaluEval, hundreds of points), and only for a
    detector that (a) has both classes and (b) still maps "no signal" (score 0) to a low probability, so a
    calibrated detector can never turn a clean response risky.
    """
    calibrators: dict[str, Calibrator] = {}
    for name, (scores, labels) in collect_scores(dataset).items():
        y = np.asarray(labels)
        if len(y) < min_points or y.sum() == 0 or y.sum() == len(y):
            continue  # too little data or one-class -> leave uncalibrated (identity)
        cal = PlattCalibrator().fit(np.asarray(scores, dtype=float), y.astype(float))
        if cal.predict_one(0.0) < 0.25:  # guard: no-evidence must stay low, or we keep identity
            calibrators[name] = cal
    return calibrators


#: Where the offline-fitted live calibrators are persisted. Fit once on a substantial labelled set (HaluEval),
#: load at startup -- the standard "fit offline, serve online" pattern, so the tiny bundled seed never has to
#: distort the live thresholds.
CALIBRATOR_ARTIFACT = Path("artifacts/calibrators.json")


def save_calibrators(calibrators: dict[str, Calibrator], path: Path = CALIBRATOR_ARTIFACT) -> None:
    """Persist the fitted Platt calibrators to a JSON artifact."""
    data = {name: cal.to_dict() for name, cal in calibrators.items() if isinstance(cal, PlattCalibrator)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def load_calibrators(path: Path = CALIBRATOR_ARTIFACT) -> dict[str, Calibrator]:
    """Load persisted calibrators if the artifact exists, else an empty map (engine falls back to identity)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {name: PlattCalibrator.from_dict(d) for name, d in data.items() if d.get("type") == "platt"}


def _prior_correct(cal: PlattCalibrator, base_rate: float) -> PlattCalibrator:
    """Re-anchor a Platt calibrator's intercept to a deployment base rate.

    HaluEval is class-balanced (~50% hallucinated), so a calibrator fit on it maps even a no-evidence score
    to that 50% prior and would over-flag mostly-clean enterprise traffic. Prior correction keeps the fitted
    slope ``a`` (the detector's discriminative power) and moves only the intercept ``b`` so a score of 0 maps
    to ``base_rate``. This is the standard base-rate adjustment (Elkan/Saerens) applied at the intercept.
    """
    cal.b = float(np.log(base_rate / (1.0 - base_rate)))
    return cal


def fit_and_save(
    limit: int = 500, path: Path = CALIBRATOR_ARTIFACT, base_rate: float = 0.03
) -> dict[str, Calibrator]:
    """Fit live calibrators on real HaluEval data (performance/groundedness axis) and persist them.

    Run once, offline: ``python -m controlplane.cascade.calibrate_live``. The artifact is loaded at startup.
    ``base_rate`` is the assumed share of genuinely-failing responses in production traffic; the fitted
    calibrators are prior-corrected to it so a clean response is not flagged just because HaluEval is balanced.
    """
    from controlplane.eval.datasets_real import load_halueval_qa

    dataset = load_halueval_qa(limit=limit)
    calibrators = fit_live_calibrators(dataset)
    calibrators = {
        name: _prior_correct(cal, base_rate) if isinstance(cal, PlattCalibrator) else cal
        for name, cal in calibrators.items()
    }
    save_calibrators(calibrators, path)
    return calibrators


if __name__ == "__main__":  # pragma: no cover - offline fitting utility
    cals = fit_and_save()
    print(f"fitted + saved {len(cals)} calibrator(s) to {CALIBRATOR_ARTIFACT}: {sorted(cals)}")
