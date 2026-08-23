"""Small runtime helpers shared across detectors -- currently just compute-device selection.

Keeps the "use the Apple M4 / a CUDA GPU when it helps, else fall back to CPU" logic in one place so every
model-backed detector picks the right device the same way, and so it is honest: if the GPU is shared/busy or
an op is unsupported, we fall back rather than crash.
"""

from __future__ import annotations

import os


def pick_device(prefer: str | None = None) -> str:
    """Return the torch device string to use: 'cuda' | 'mps' | 'cpu'.

    Order: an explicit override (``prefer`` arg or ``CONTROLPLANE_DEVICE`` env) wins; then CUDA (A100/any
    NVIDIA); then Apple Metal (M-series) via MPS; else CPU. Never raises -- if torch is absent it returns cpu.
    """
    forced = prefer or os.environ.get("CONTROLPLANE_DEVICE")
    if forced:
        return forced
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001 - torch not installed / probe failed -> CPU is always safe
        pass
    return "cpu"
