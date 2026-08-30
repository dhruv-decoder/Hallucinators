"""Model-backed groundedness: Vectara HHEM-2.1-Open, the realised upgrade of the lexical heuristic.

The T0 ``GroundednessHeuristicDetector`` measures word overlap; it cannot tell that "refunds within 180 days"
contradicts a source that says "30 days" if they happen to share words. HHEM-2.1-Open is a cross-encoder
trained for exactly this: given (premise=source, hypothesis=claim) it returns a factual-consistency score in
[0, 1] (1 = fully supported). Groundedness *risk* is ``1 - max consistency over the retrieved chunks``.

It is a real model but a light one -- it runs on CPU in <600 MB and ~1.5 s for a 2k-token input -- so it is a
sensible **T1** check the VoI rule can climb to when the cheap T0 signals leave the axis uncertain. It is
optional (the ``[ml]`` extra pulls in ``transformers`` + ``torch``); the model is loaded lazily on first use
and cached process-wide, and the engine falls back to the lexical heuristic when it is not installed. Model:
``vectara/hallucination_evaluation_model``.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

_MODEL_ID = "vectara/hallucination_evaluation_model"


@lru_cache(maxsize=1)
def _get_model():
    """Load and cache the HHEM cross-encoder on the best available device (M4 GPU / CUDA / CPU).

    Validates the chosen device with a tiny prediction and falls back to CPU if an op is unsupported there
    (Metal/MPS does not implement every kernel), so enabling the GPU can never break the pipeline.
    """
    try:
        from transformers import AutoModelForSequenceClassification
    except ImportError as exc:  # pragma: no cover - only without the [ml] extra
        raise ImportError(
            "HHEMGroundednessDetector needs the '[ml]' extra: pip install -e '.[ml]'"
        ) from exc

    from controlplane.runtime import pick_device

    model = AutoModelForSequenceClassification.from_pretrained(_MODEL_ID, trust_remote_code=True)
    device = pick_device()
    if device != "cpu":
        try:
            model = model.to(device)
            model.predict([("the sky is blue", "the sky is blue")])  # smoke-test the device
        except Exception:  # noqa: BLE001 - unsupported op on this device -> CPU
            model = model.to("cpu")
    return model


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
        """True if the optional deps are importable AND on a compatible transformers version.

        HHEM-2.1-Open's vendored model code needs transformers 4.x; on 5.x the checkpoint loads with
        newly-initialised (random) embeddings and would silently emit garbage. Rather than mis-score, we
        report unavailable so the engine falls back to the honest lexical heuristic (and the dashboard shows
        ``lexical-heuristic`` instead of claiming ``hhem-2.1``). Pin with the ``[ml]`` extra (transformers<5).
        """
        if not (importlib.util.find_spec("transformers") and importlib.util.find_spec("torch")):
            return False
        try:
            import transformers

            if int(transformers.__version__.split(".")[0]) >= 5:
                return False
        except Exception:  # noqa: BLE001 - if the version can't be parsed, let the loader try
            pass
        return True

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
