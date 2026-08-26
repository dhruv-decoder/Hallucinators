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
