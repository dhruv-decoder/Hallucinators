"""Cost-axis detectors: is there a cheaper path to the same quality?

The cost axis is the funding side of oversight. These detectors do not estimate a failure probability;
they surface opportunities (route down to a smaller model, serve from cache) that the P&L ledger books
as savings. Those savings are what subsidise the performance and responsibility checks.

Today: a model-overkill heuristic and an exact-normalised semantic cache (T0). Upgrade path: a learned
router (RouteLLM class) and an embedding-based near-duplicate cache. The ledger, not the detector, owns
pricing, so savings are computed in one place. See docs/PLAN.md section 8.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.base import CostDetector
from controlplane.core.types import CostAction, CostOpportunity, RequestContext, Tier

# Substrings that mark a model as a high-cost "flagship" whose work can often be routed down.
_FLAGSHIP_HINTS = ("gpt-4", "opus", "-large", "ultra", "flagship")
# Substrings that mark an already-cheap model, which should never be flagged as a flagship even if it
# also matches a flagship hint (e.g. "gpt-4o-mini" contains "gpt-4").
_CHEAP_HINTS = ("mini", "small", "nano", "lite", "flash", "haiku", "tiny")
# Markers that a prompt is genuinely hard, so routing down would risk quality.
_COMPLEXITY_MARKERS = re.compile(
    r"```|\bprove\b|\bderive\b|\bstep by step\b|\banalyze\b|\bwrite code\b|\brefactor\b|\bSQL\b",
    re.IGNORECASE,
)


def _normalize(prompt: str) -> str:
    return " ".join(prompt.lower().split())


# Flagship -> cheaper model for a genuine route-down (used by the proxy to actually invoke the cheaper model).
_ROUTE_TARGET = {
    "openai/gpt-oss-120b": "openai/gpt-oss-20b",
    "gpt-4o": "gpt-4o-mini",
    "gpt-5": "gpt-5-mini",
    "claude-opus-5": "claude-haiku-4.5",
    "claude-sonnet-5": "claude-haiku-4.5",
}


def suggest_route_down(model: str | None, prompt: str, simple_word_limit: int = 40) -> str | None:
    """Return a cheaper model to actually call for a simple prompt on a flagship, or None to keep the model.

    "Simple" = short and free of complexity markers (code fences, proofs, multi-step analysis). This is the
    same rule the ``ModelOverkillDetector`` uses to *recommend* route-down; the proxy uses it to *execute* one.
    """
    if not model or model not in _ROUTE_TARGET:
        return None
    if len(prompt.split()) > simple_word_limit or _COMPLEXITY_MARKERS.search(prompt):
        return None
    return _ROUTE_TARGET[model]


def _is_flagship(model: str, ctx: RequestContext) -> bool:
    tier_hint = str(ctx.meta.get("model_tier", "")).lower()
    if tier_hint == "flagship":
        return True
    model_l = model.lower()
    if any(h in model_l for h in _CHEAP_HINTS):
        return False
    return any(h in model_l for h in _FLAGSHIP_HINTS)


class ModelOverkillDetector(CostDetector):
    """Recommend routing simple prompts on a flagship model down to a cheaper one.

    "Simple" here means short and free of complexity markers (code fences, proofs, multi-step analysis).
    The detector only recommends; the ledger computes the dollar savings from the pricing table and the
    policy decides whether to apply it.
    """

    name = "model_overkill"
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0

    def __init__(self, simple_word_limit: int = 40, cheaper_model: str = "gpt-4o-mini") -> None:
        self._limit = simple_word_limit
        self._cheaper = cheaper_model

    def assess(self, ctx: RequestContext) -> CostOpportunity:
        words = len(ctx.prompt.split())
        complex_prompt = bool(_COMPLEXITY_MARKERS.search(ctx.prompt))
        overkill = (
            _is_flagship(ctx.model, ctx)
            and ctx.model != self._cheaper
            and words <= self._limit
            and not complex_prompt
        )
        detail = {
            "prompt_words": words,
            "flagship": _is_flagship(ctx.model, ctx),
            "complex": complex_prompt,
        }
        if overkill:
            return CostOpportunity(
                name=self.name,
                tier=self.tier,
                recommendation=CostAction.ROUTE_DOWN,
                detail={**detail, "suggested_model": self._cheaper},
            )
        return CostOpportunity(
            name=self.name, tier=self.tier, recommendation=CostAction.NONE, detail=detail
        )


class SemanticCacheDetector(CostDetector):
    """Serve a repeated request from cache instead of paying for the model again.

    This reference implementation matches on the exact normalised prompt (lowercased, whitespace
    collapsed) using an in-process store. The production upgrade is an embedding near-duplicate cache so
    paraphrases also hit. A cache hit lets the ledger book the entire model call as saved.
    """

    name = "semantic_cache"
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def assess(self, ctx: RequestContext) -> CostOpportunity:
        key = _normalize(ctx.prompt)
        if key and key in self._seen:
            return CostOpportunity(
                name=self.name,
                tier=self.tier,
                recommendation=CostAction.CACHE_HIT,
                detail={"cache": "hit"},
            )
        if key:
            self._seen.add(key)
        return CostOpportunity(
            name=self.name, tier=self.tier, recommendation=CostAction.NONE, detail={"cache": "miss"}
        )
