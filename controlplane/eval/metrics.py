"""Confusion-matrix metrics for detection quality.

These answer the brief's "report false positive / false negative rates to a skeptical stakeholder"
directly. All rates guard against division by zero (an undefined rate is reported as 0.0). Point estimates on
a finite eval set carry sampling noise, so we also provide confidence intervals: a Wilson score interval for
simple proportions (recall, precision) and a percentile bootstrap for F1 (which is not a single proportion).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ConfusionMatrix:
    """Counts of true/false positives and negatives, with the standard rates derived from them."""

    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def fpr(self) -> float:
        """False positive rate: of the truly-clean cases, how many we wrongly flagged (alert fatigue)."""
        denom = self.fp + self.tn
        return self.fp / denom if denom else 0.0

    @property
    def fnr(self) -> float:
        """False negative rate: of the true failures, how many we missed (liability)."""
        denom = self.fn + self.tp
        return self.fn / denom if denom else 0.0

    def recall_ci(self, z: float = 1.96) -> tuple[float, float]:
        """95%-by-default Wilson interval for recall = tp / (tp + fn)."""
        return wilson_interval(self.tp, self.tp + self.fn, z)

    def precision_ci(self, z: float = 1.96) -> tuple[float, float]:
        """95%-by-default Wilson interval for precision = tp / (tp + fp)."""
        return wilson_interval(self.tp, self.tp + self.fp, z)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (better than normal approx for small n / extreme p).

    ``z`` is the standard-normal quantile: 1.96 for 95%. Returns (0, 0) for an empty denominator.
    """
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_f1_ci(
    y_true: Sequence[bool], y_pred: Sequence[bool], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI for F1. F1 is not a single proportion, so we resample the paired examples.

    Uses numpy for the resample so it stays fast at eval-set sizes (thousands of rows x thousands of draws).
    """
    import numpy as np

    yt = np.asarray(y_true, dtype=bool)
    yp = np.asarray(y_pred, dtype=bool)
    n = len(yt)
    if n == 0:
        return (0.0, 0.0)
    idx = np.random.default_rng(seed).integers(0, n, size=(n_boot, n))
    st, sp = yt[idx], yp[idx]
    tp = (st & sp).sum(axis=1)
    fp = (~st & sp).sum(axis=1)
    fn = (st & ~sp).sum(axis=1)
    denom = 2 * tp + fp + fn
    f1 = np.divide(
        2 * tp,
        denom,
        out=np.zeros_like(denom, dtype=float),
        where=denom > 0,
    )
    lo, hi = np.quantile(f1, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def confusion(y_true: list[bool], y_pred: list[bool]) -> ConfusionMatrix:
    """Build a confusion matrix from aligned truth and prediction lists."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    tp = fp = fn = tn = 0
    for truth, pred in zip(y_true, y_pred, strict=True):
        if truth and pred:
            tp += 1
        elif not truth and pred:
            fp += 1
        elif truth and not pred:
            fn += 1
        else:
            tn += 1
    return ConfusionMatrix(tp=tp, fp=fp, fn=fn, tn=tn)
