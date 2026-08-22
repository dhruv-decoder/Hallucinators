"""Performance-axis detectors: is the answer wrong, or confidently wrong?

Today, three lightweight signals:

- ``OverconfidenceDetector`` (T0) -- assertive language with no hedging. A weak prior on its own; it
  matters most combined with a correctness signal (the confidently-wrong quadrant).
- ``GroundednessHeuristicDetector`` (T1) -- lexical support of the response by the retrieved context.
- ``SelfConsistencyDetector`` (T1) -- disagreement across independent samples of the same prompt.

Upgrade path: groundedness -> HHEM-2.1 / MiniCheck; self-consistency -> semantic entropy via an NLI or
embedding model; overconfidence -> white-box Semantic-Entropy Probes on a locally served model. Each
heuristic here is a faithful but cruder stand-in, documented as such. See docs/PLAN.md section 8.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

_ASSERTIVE = re.compile(
    r"\b(definitely|certainly|guaranteed|undoubtedly|absolutely|always|never|"
    r"100%|without a doubt|clearly|obviously|no doubt)\b",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"\b(might|may|maybe|possibly|perhaps|likely|approximately|around|about|"
    r"i think|i believe|it seems|appears|roughly|could be|not sure)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class OverconfidenceDetector(Detector):
    """Flag assertive, unhedged phrasing as a weak prior on overconfidence.

    This does not know whether the answer is correct; it measures tone. Its value is realised when the
    engine pairs it with a correctness signal (groundedness / self-consistency) -- high assertiveness
    plus low correctness is the dangerous confidently-wrong quadrant.
    """

    name = "overconfidence"
    axis = Axis.PERFORMANCE
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0
    informativeness = 0.25

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        text = ctx.response or ""
        assertive = len(_ASSERTIVE.findall(text))
        hedge = len(_HEDGE.findall(text))
        # More assertive markers raise risk; hedging lowers it. Squashed to [0, 1).
        raw = assertive - hedge
        score = 1.0 - 0.6 ** max(raw, 0) if raw > 0 else 0.0
        return score, {"assertive_markers": assertive, "hedge_markers": hedge}


class GroundednessHeuristicDetector(Detector):
    """Estimate how well the response is supported by the retrieved context (lexical proxy for NLI).

    Abstains (score 0, flagged in detail) when there is no retrieved context -- we never invent a
    groundedness verdict where there is nothing to ground against. Real deployment swaps this for
    HHEM-2.1 / MiniCheck, which do entailment rather than word overlap.
    """

    name = "groundedness_heuristic"
    axis = Axis.PERFORMANCE
    tier = Tier.T0  # lexical overlap is free; the model-based upgrade (HHEM/MiniCheck) is the T1 version
    est_cost_usd = 0.0
    est_latency_ms = 2.0
    informativeness = 0.65

    def applicable(self, ctx: RequestContext) -> bool:
        return bool(ctx.retrieved_context)

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        if not ctx.retrieved_context:
            return 0.0, {"abstained": True, "reason": "no retrieved context to check against"}
        response_tokens = _tokens(ctx.response)
        if not response_tokens:
            return 0.0, {"abstained": True, "reason": "empty response"}
        context_tokens: set[str] = set()
        for chunk in ctx.retrieved_context:
            context_tokens |= _tokens(chunk)
        # Fraction of response content words that appear in the source. Low support -> high risk.
        supported = len(response_tokens & context_tokens) / len(response_tokens)
        score = 1.0 - supported
        return score, {"support_fraction": round(supported, 4)}


class SelfConsistencyDetector(Detector):
    """Estimate answer uncertainty from disagreement across independent samples.

    Needs at least one extra sample beyond the primary response; abstains otherwise. Uses mean pairwise
    token-set dissimilarity as a cheap stand-in for semantic entropy (which clusters by meaning using an
    NLI/embedding model). Wide disagreement across samples signals the model is guessing.
    """

    name = "self_consistency"
    axis = Axis.PERFORMANCE
    tier = Tier.T1
    # Nominal per-run cost estimate the VoI gate weighs (drawing extra samples is not free). The P&L
    # ledger books the true cost from the actual token counts; this is only the gate's prior.
    est_cost_usd = 0.002
    est_latency_ms = 30.0
    informativeness = 0.6

    def applicable(self, ctx: RequestContext) -> bool:
        return len(ctx.samples) >= 1

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        answers = [ctx.response, *ctx.samples] if ctx.response else list(ctx.samples)
        answers = [a for a in answers if a]
        if len(answers) < 2:
            return 0.0, {"abstained": True, "reason": "need >=2 samples for self-consistency"}
        token_sets = [_tokens(a) for a in answers]
        sims: list[float] = []
        for i in range(len(token_sets)):
            for j in range(i + 1, len(token_sets)):
                sims.append(_jaccard(token_sets[i], token_sets[j]))
        mean_similarity = sum(sims) / len(sims)
        score = 1.0 - mean_similarity
        return score, {"n_samples": len(answers), "mean_similarity": round(mean_similarity, 4)}
