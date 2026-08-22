"""Confusion-matrix metrics for detection quality.

These answer the brief's "report false positive / false negative rates to a skeptical stakeholder"
directly. All rates guard against division by zero (an undefined rate is reported as 0.0).
"""

from __future__ import annotations

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
