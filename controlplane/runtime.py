"""Small runtime helpers shared across detectors -- currently just compute-device selection.

Keeps the "use the Apple M4 / a CUDA GPU when it helps, else fall back to CPU" logic in one place so every
model-backed detector picks the right device the same way, and so it is honest: if the GPU is shared/busy or
an op is unsupported, we fall back rather than crash.
"""

from __future__ import annotations

import os
import pathlib


def load_dotenv(path: str = ".env") -> None:
    """Load ``KEY=VALUE`` pairs from a local ``.env`` into the environment (existing vars win).

    Dependency-free so the core has no new requirement. Used to pick up secrets like ``GROQ_API_KEY`` for the
    optional real-model paths without ever committing them. Values may be quoted and may carry an inline
    ``# comment``. Missing file is a no-op.
    """
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


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
