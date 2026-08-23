"""Build the best detector stack available in this environment.

The same code runs on a laptop with nothing installed (heuristics only) and on a box with the ``[ml]`` extra
and/or a judge backend (model-backed groundedness + a T2 LLM judge). The factory probes what is available and
assembles the detector list accordingly, so ``oversight``, the demos, the eval harness, and the agent auditor
all get the strongest stack without any of them hard-coding model dependencies.

Defaults are conservative and offline-safe:

- **groundedness** -- always the lexical T0 heuristic; *plus* HHEM-2.1-Open at T1 if ``transformers``/``torch``
  are importable (the VoI rule decides when to climb to it).
- **PII** -- always the regex T0; *plus* Presidio NER only when ``CONTROLPLANE_USE_PRESIDIO`` is set (it needs a
  one-time spaCy model download, so it is opt-in rather than auto).
- **judge (T2)** -- added only when a backend is reachable (a provider key for litellm, or a local Ollama).

Every model-backed detector degrades to abstaining if it fails at runtime, so enabling one can never 500 a
request; the worst case is falling back to the cheaper signal.
"""

from __future__ import annotations

import importlib.util
import os

from controlplane.cascade.detectors.base import CostDetector, Detector
from controlplane.cascade.detectors.cost import ModelOverkillDetector, SemanticCacheDetector
from controlplane.cascade.detectors.groundedness_model import HHEMGroundednessDetector
from controlplane.cascade.detectors.judge import LlmJudgeDetector
from controlplane.cascade.detectors.performance import (
    GroundednessHeuristicDetector,
    OverconfidenceDetector,
    SelfConsistencyDetector,
)
from controlplane.cascade.detectors.responsibility import RegexPiiDetector
from controlplane.cascade.detectors.safety import PromptInjectionDetector, UnsafeContentDetector


def _models_disabled() -> bool:
    """Force heuristics-only when ``CONTROLPLANE_MODELS`` is off/none/heuristic.

    This is how the reproducible eval and the deterministic test suite pin the stack regardless of what
    happens to be installed or listening locally; the live server leaves it unset and auto-detects.
    """
    return os.environ.get("CONTROLPLANE_MODELS", "auto").lower() in ("off", "none", "heuristic")


def _presidio_requested() -> bool:
    if os.environ.get("CONTROLPLANE_USE_PRESIDIO", "").lower() not in ("1", "true", "yes"):
        return False
    return bool(importlib.util.find_spec("presidio_analyzer") and importlib.util.find_spec("spacy"))


def build_failure_detectors(
    use_hhem: bool | None = None,
    use_presidio: bool | None = None,
    use_judge: bool | None = None,
    judge_model: str | None = None,
) -> list[Detector]:
    """Assemble the performance + responsibility detector list, adding model-backed tiers when available."""
    performance: list[Detector] = [
        OverconfidenceDetector(),
        GroundednessHeuristicDetector(),
        SelfConsistencyDetector(),
    ]
    responsibility: list[Detector] = [
        RegexPiiDetector(),
        PromptInjectionDetector(),
        UnsafeContentDetector(),
    ]

    disabled = _models_disabled()
    if use_hhem is None:
        use_hhem = False if disabled else HHEMGroundednessDetector.available()
    if use_hhem:
        try:
            performance.append(HHEMGroundednessDetector())
        except Exception:  # noqa: BLE001 - never let an optional detector block startup
            pass

    if use_presidio is None:
        use_presidio = False if disabled else _presidio_requested()
    if use_presidio:
        try:
            from controlplane.cascade.detectors.responsibility_ml import PresidioPiiDetector

            responsibility.append(PresidioPiiDetector())
        except Exception:  # noqa: BLE001
            pass

    if use_judge is None:
        use_judge = False if disabled else LlmJudgeDetector.available()[0]
    if use_judge:
        try:
            performance.append(LlmJudgeDetector(model=judge_model))
        except Exception:  # noqa: BLE001
            pass

    return performance + responsibility


def build_cost_detectors() -> list[CostDetector]:
    """The cost-axis (funding) detectors -- shared, since the cache is stateful."""
    return [ModelOverkillDetector(), SemanticCacheDetector()]


def active_models() -> dict[str, str]:
    """Report which real models are active vs the heuristic fallback -- for /healthz and the dashboard."""
    if _models_disabled():
        return {"groundedness": "lexical-heuristic", "pii": "regex-heuristic", "judge": "disabled"}
    judge_ok, backend = LlmJudgeDetector.available()
    return {
        "groundedness": "hhem-2.1-open" if HHEMGroundednessDetector.available() else "lexical-heuristic",
        "pii": "presidio-ner" if _presidio_requested() else "regex-heuristic",
        "judge": backend if judge_ok else "disabled",
    }
