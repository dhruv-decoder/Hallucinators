"""Test-suite configuration.

Pin the detector factory to heuristics-only for the whole suite so tests are deterministic and never reach a
locally-installed model or a running judge backend (e.g. Ollama on :11434). Tests that specifically exercise
the model-backed path pass explicit arguments or monkeypatch the model call, which override this default.
"""

import os

os.environ["CONTROLPLANE_MODELS"] = "off"
