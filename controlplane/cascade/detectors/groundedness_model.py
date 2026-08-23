"""Model-backed groundedness: Vectara HHEM-2.1-Open, the realised upgrade of the lexical heuristic.

The T0 ``GroundednessHeuristicDetector`` measures word overlap; it cannot tell that "refunds within 180 days"
contradicts a source that says "30 days" if they happen to share words. HHEM-2.1-Open is a cross-encoder
trained for exactly this: given (premise=source, hypothesis=claim) it returns a factual-consistency score in
[0, 1] (1 = fully supported). Groundedness *risk* is ``1 - max consistency over the retrieved chunks``.

It is a real model but a light one -- it runs on CPU in <600 MB and ~1.5 s for a 2k-token input -- so it is a
sensible **T1** check the VoI rule can climb to when the cheap T0 signals leave the axis uncertain. It is
optional (the ``[ml]`` extra pulls in ``transformers`` + ``torch``); the model is loaded lazily on first use
and cached process-wide, and the engine falls back to the lexical heuristic when it is not installed. Model:
``vectara/hallucination_evaluation_model`` (see docs/EVIDENCE.md).
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

_MODEL_ID = "vectara/hallucination_evaluation_model"


@lru_cache(maxsize=1)
def _get_model():
    """Load and cache the HHEM cross-encoder. Raises ImportError if the optional deps are missing."""
    try:
        from transformers import AutoModelForSequenceClassification
    except ImportError as exc:  # pragma: no cover - only without the [ml] extra
        raise ImportError(
            "HHEMGroundednessDetector needs the '[ml]' extra: pip install -e '.[ml]'"
        ) from exc
    return AutoModelForSequenceClassification.from_pretrained(_MODEL_ID, trust_remote_code=True)


class HHEMGroundednessDetector(Detector):
    """Estimate groundedness risk with the HHEM-2.1-Open factual-consistency cross-encoder (T1)."""

    name = "hhem_groundedness"
    axis = Axis.PERFORMANCE
    tier = Tier.T1
    est_cost_usd = 0.0  # local inference: compute, not dollars
    est_latency_ms = 200.0  # nominal gate estimate; the real cost is metered from the signal timing
    informativeness = 0.8

    @classmethod
    def available(cls) -> bool:
        """True if the optional deps are importable (does not load the model)."""
        return bool(importlib.util.find_spec("transformers") and importlib.util.find_spec("torch"))

    def applicable(self, ctx: RequestContext) -> bool:
        return bool(ctx.retrieved_context and (ctx.response or "").strip())

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        chunks = [c for c in ctx.retrieved_context if c and c.strip()]
        if not chunks or not (ctx.response or "").strip():
            return 0.0, {"abstained": True, "reason": "no context or empty response"}
        try:
            model = _get_model()
            # HHEM scores (premise=source, hypothesis=claim); take the best-supporting chunk.
            scores = model.predict([(chunk, ctx.response) for chunk in chunks])
            consistency = max(float(s) for s in scores)
        except Exception as exc:  # noqa: BLE001 - a model load/inference failure must not break the pipeline
            return 0.0, {"abstained": True, "reason": f"hhem unavailable: {exc}"}
        return 1.0 - consistency, {"hhem_consistency": round(consistency, 4), "chunks": len(chunks)}
