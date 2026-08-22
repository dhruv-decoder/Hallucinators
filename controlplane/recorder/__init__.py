"""The flight recorder: turns decisions into hash-chained, tamper-evident receipts and stores them."""

from controlplane.recorder.receipt import build_receipt, compute_hash
from controlplane.recorder.store import JsonlRecorder

__all__ = ["build_receipt", "compute_hash", "JsonlRecorder"]
