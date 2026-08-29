"""Probability calibration for detector scores.

The VoI stopping rule (``voi.py``) treats ``p_fail`` as a genuine probability. Raw detector scores are
usually not: a groundedness model might emit 0.7 for cases that are actually wrong only 40% of the time.
Calibration learns a mapping from raw score to true failure rate on held-out labelled data, so the
expected-loss arithmetic is grounded in reality and we can show a reliability diagram to a skeptic.

Two standard methods are implemented from first principles (no sklearn dependency) so the team can
explain every step:

- ``PlattCalibrator``  -- fit a sigmoid ``1 / (1 + exp(-(a*score + b)))`` by logistic regression.
- ``IsotonicCalibrator`` -- fit a monotone step function via Pool-Adjacent-Violators (PAV).

``expected_calibration_error`` reports how far off we are, for the eval report.
"""

from __future__ import annotations

import abc

import numpy as np


class Calibrator(abc.ABC):
    """Maps raw detector scores in [0, 1] to calibrated failure probabilities in [0, 1]."""

    @abc.abstractmethod
    def fit(self, scores: np.ndarray, labels: np.ndarray) -> Calibrator: ...

    @abc.abstractmethod
    def predict(self, scores: np.ndarray) -> np.ndarray: ...

    def predict_one(self, score: float) -> float:
        """Convenience for the engine: calibrate a single score to a single probability."""
        return float(self.predict(np.asarray([score], dtype=float))[0])


class IdentityCalibrator(Calibrator):
    """No-op calibrator: uses the raw score as the probability.

    This is the honest default before any labelled data exists -- we say the score is uncalibrated
    rather than pretend otherwise.
    """

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> IdentityCalibrator:
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        return np.clip(np.asarray(scores, dtype=float), 0.0, 1.0)


class PlattCalibrator(Calibrator):
    """Sigmoid (logistic) calibration: ``p = 1 / (1 + exp(-(a*score + b)))``.

    Fit by gradient descent on the log-loss. Uses Platt's target smoothing -- positives target
    ``(N+ + 1)/(N+ + 2)`` and negatives target ``1/(N- + 2)`` -- to avoid overconfident fits on small
    or separable data.
    """

    def __init__(self, iters: int = 2000, lr: float = 0.5) -> None:
        self.a: float = 1.0
        self.b: float = 0.0
        self.fitted: bool = False
        self._iters = iters
        self._lr = lr

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> PlattCalibrator:
        x = np.asarray(scores, dtype=float)
        y = np.asarray(labels, dtype=float)
        n_pos = float(y.sum())
        n_neg = float(len(y) - n_pos)
        hi = (n_pos + 1.0) / (n_pos + 2.0)
        lo = 1.0 / (n_neg + 2.0)
        target = np.where(y > 0.5, hi, lo)

        a, b = 0.0, 0.0
        for _ in range(self._iters):
            z = np.clip(a * x + b, -30.0, 30.0)
            p = 1.0 / (1.0 + np.exp(-z))
            grad_a = float(np.mean((p - target) * x))
            grad_b = float(np.mean(p - target))
            a -= self._lr * grad_a
            b -= self._lr * grad_b
        self.a, self.b, self.fitted = a, b, True
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        x = np.asarray(scores, dtype=float)
        if not self.fitted:
            return np.clip(x, 0.0, 1.0)
        z = np.clip(self.a * x + self.b, -30.0, 30.0)
        return 1.0 / (1.0 + np.exp(-z))

    def to_dict(self) -> dict:
        """Serialize the fitted parameters so calibrators can be persisted to an artifact and reloaded."""
        return {"type": "platt", "a": self.a, "b": self.b, "fitted": self.fitted}

    @classmethod
    def from_dict(cls, d: dict) -> PlattCalibrator:
        c = cls()
        c.a, c.b, c.fitted = float(d["a"]), float(d["b"]), bool(d.get("fitted", True))
        return c


class IsotonicCalibrator(Calibrator):
    """Monotone non-decreasing calibration via Pool-Adjacent-Violators (PAV).

    PAV finds the least-squares non-decreasing fit to the labels ordered by score. It is more flexible
    than Platt (no sigmoid shape assumption) but needs more data to be stable. Prediction interpolates
    linearly between the fitted points.
    """

    def __init__(self) -> None:
        self._x: np.ndarray | None = None
        self._y: np.ndarray | None = None

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> IsotonicCalibrator:
        x = np.asarray(scores, dtype=float)
        y = np.asarray(labels, dtype=float)
        order = np.argsort(x, kind="mergesort")
        x_sorted = x[order]
        y_sorted = y[order]
        fitted = _pav(y_sorted)

        # Collapse duplicate scores so np.interp sees strictly increasing x, and enforce monotonicity.
        ux, inverse = np.unique(x_sorted, return_inverse=True)
        counts = np.bincount(inverse).astype(float)
        summed = np.zeros_like(ux, dtype=float)
        np.add.at(summed, inverse, fitted)
        uy = np.maximum.accumulate(summed / counts)
        self._x, self._y = ux, uy
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        x = np.asarray(scores, dtype=float)
        if self._x is None or self._y is None:
            return np.clip(x, 0.0, 1.0)
        return np.clip(np.interp(x, self._x, self._y), 0.0, 1.0)


def _pav(y: np.ndarray) -> np.ndarray:
    """Pool-Adjacent-Violators: least-squares non-decreasing fit to ``y`` (already ordered by score).

    Walks left to right maintaining blocks of equal fitted value; whenever a new point would make the
    sequence decrease, it merges blocks (weighted mean) until monotonicity is restored.
    """
    values: list[float] = []
    weights: list[float] = []
    counts: list[int] = []
    for target in y:
        v = float(target)
        w = 1.0
        c = 1
        while values and values[-1] > v:
            pv = values.pop()
            pw = weights.pop()
            pc = counts.pop()
            v = (pv * pw + v * w) / (pw + w)
            w = pw + w
            c = pc + c
        values.append(v)
        weights.append(w)
        counts.append(c)

    out = np.empty(len(y), dtype=float)
    idx = 0
    for v, c in zip(values, counts, strict=False):
        out[idx : idx + c] = v
        idx += c
    return out


def expected_calibration_error(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 10
) -> float:
    """Expected Calibration Error: average gap between predicted confidence and observed accuracy.

    Bins predictions into ``n_bins`` equal-width buckets and returns the sample-weighted mean of
    ``|confidence - accuracy|`` across non-empty buckets. 0 is perfectly calibrated.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if len(p) == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bucket = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    ece = 0.0
    n = len(p)
    for b in range(n_bins):
        mask = bucket == b
        count = int(mask.sum())
        if count == 0:
            continue
        confidence = float(p[mask].mean())
        accuracy = float(y[mask].mean())
        ece += (count / n) * abs(confidence - accuracy)
    return ece


def reliability_curve(
    probs: np.ndarray, labels: np.ndarray, n_bins: int = 10
) -> dict[str, list[float]]:
    """Return per-bin confidence, accuracy, and count for plotting a reliability diagram."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bucket = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    confidences: list[float] = []
    accuracies: list[float] = []
    counts: list[float] = []
    for b in range(n_bins):
        mask = bucket == b
        count = int(mask.sum())
        if count == 0:
            continue
        confidences.append(float(p[mask].mean()))
        accuracies.append(float(y[mask].mean()))
        counts.append(float(count))
    return {"confidence": confidences, "accuracy": accuracies, "count": counts}
