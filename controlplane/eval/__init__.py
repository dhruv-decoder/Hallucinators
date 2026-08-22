"""Evaluation harness: measure detection quality (P/R/F1/FPR/FNR), baselines, cost, and calibration."""

from controlplane.eval.harness import EvalReport, run_harness
from controlplane.eval.metrics import ConfusionMatrix, confusion

__all__ = ["run_harness", "EvalReport", "confusion", "ConfusionMatrix"]
