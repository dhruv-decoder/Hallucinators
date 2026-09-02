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
import threading

from controlplane.cascade.detectors.abstention import split_abstention
from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

_MODEL_ID = "vectara/hallucination_evaluation_model"


#: The loaded cross-encoder, and the lock that guarantees exactly one thread ever builds it. The engine
#: runs detectors on worker threads (``asyncio.to_thread``), so without this the first few concurrent
#: requests all miss the cache and call ``from_pretrained`` at once. HHEM's vendored loading code
#: materialises weights through accelerate's meta-device path, and interleaving two of those leaves one
#: model with meta tensors that only fail later, at inference, with "Tensor.item() cannot be called on
#: meta tensors". Double-checked locking makes the load happen once and the failure impossible.
_MODEL = None
_LOAD_LOCK = threading.Lock()


def _get_model():
    """Load and cache the HHEM cross-encoder on the best available device (M4 GPU / CUDA / CPU).

    Validates the chosen device with a tiny prediction and falls back to CPU if an op is unsupported there
    (Metal/MPS does not implement every kernel), so enabling the GPU can never break the pipeline.
    """
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _LOAD_LOCK:
        if _MODEL is None:  # another thread may have finished while this one waited
            _MODEL = _build_model()
        return _MODEL


def _build_model():
    """Materialise the model. Only ever called with ``_LOAD_LOCK`` held."""
    try:
        from transformers import AutoModelForSequenceClassification
    except ImportError as exc:  # pragma: no cover - only without the [ml] extra
        raise ImportError(
            "HHEMGroundednessDetector needs the '[ml]' extra: pip install -e '.[ml]'"
        ) from exc

    from controlplane.runtime import pick_device

    def _load(device: str):
        """Load a fresh instance on ``device``, proving it works before it is handed back."""
        m = AutoModelForSequenceClassification.from_pretrained(_MODEL_ID, trust_remote_code=True)
        if device != "cpu":
            m = m.to(device)
        m.predict([("the sky is blue", "the sky is blue")])  # smoke-test this exact instance
        return m

    device = pick_device()
    if device == "cpu":
        return _load("cpu")
    try:
        return _load(device)
    except Exception:  # noqa: BLE001 - accelerator unavailable, busy, or missing an op
        # Reload from scratch rather than moving the failed object. A model that was materialised with meta
        # tensors cannot be moved to CPU either, so `.to("cpu")` on it raises again and the detector ends up
        # abstaining on every request while reporting itself healthy. Building a clean CPU instance is the
        # only fallback that actually recovers.
        return _load("cpu")


class HHEMGroundednessDetector(Detector):
    """Estimate groundedness risk with the HHEM-2.1-Open factual-consistency cross-encoder (T1)."""

    name = "hhem_groundedness"
    axis = Axis.PERFORMANCE
    tier = Tier.T1
    est_cost_usd = 0.0  # local inference: compute, not dollars
    est_latency_ms = 200.0  # nominal gate estimate; the real cost is metered from the signal timing
    informativeness = 0.8
    construct = "groundedness"  # the model-backed upgrade of the lexical proxy, not extra evidence beside it

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
        # NLI entailment of a refusal is always low -- not because the model hallucinated but because it
        # asserted nothing. Score the claim-bearing part only; abstain on a pure refusal. See abstention.py.
        claim, declined = split_abstention(ctx.response)
        if declined and not claim:
            return 0.0, {"abstained": True, "reason": "response declined to answer; no claim to ground"}
        hypothesis = claim or ctx.response
        try:
            model = _get_model()
            # HHEM scores (premise=source, hypothesis=claim); take the best-supporting chunk.
            scores = model.predict([(chunk, hypothesis) for chunk in chunks])
            consistency = max(float(s) for s in scores)
        except Exception as exc:  # noqa: BLE001 - a model load/inference failure must not break the pipeline
            return 0.0, {"abstained": True, "unavailable": True, "reason": f"hhem unavailable: {exc}"}
        detail = {"hhem_consistency": round(consistency, 4), "chunks": len(chunks)}
        if declined:
            detail["abstention_clauses_ignored"] = len(declined)
        return 1.0 - consistency, detail
