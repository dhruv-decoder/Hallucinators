"""Responsibility-axis bias detector -- the gap the brief (and our own proposal) named but we hadn't built.

The brief calls out bias as a first-class responsibility risk that *overlaps* hallucination and privacy: a
biased judgement about a person is its own harm. This T0 detector flags the dangerous pattern directly -- a
**protected attribute** (race / gender / religion / age / nationality / disability) mentioned together with
**loaded decision or stereotype language** ("less qualified", "more likely to default", "those people",
"should be denied"). Requiring *both* keeps neutral, respectful mentions ("our diverse team") at score 0.

This is an honest, specific heuristic, not a fairness oracle. Its documented upgrade is **output-level
counterfactual demographic testing** (swap the protected attribute, re-query the model, and measure whether
the decision / sentiment / refusal changes -- BiasGuard-style), which needs the model in the loop and so lives
in the proxy/eval layer; and a reasoning bias-detection model on the tail. See docs/ASSESSMENT.md section 5.2.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

# Protected-attribute mentions (a person-group is being singled out).
_PROTECTED = re.compile(
    r"\b(black|white|asian|hispanic|latino|latina|african|arab|jewish|muslim|christian|hindu|sikh|"
    r"buddhist|men|women|man|woman|male|female|transgender|nonbinary|gay|lesbian|queer|elderly|"
    r"disabled|immigrant|refugee|caste|dalit|indigenous|foreigner)s?\b",
    re.IGNORECASE,
)

# Loaded decision / stereotype language applied to a group.
_LOADED = re.compile(
    r"\b(less (qualified|capable|competent|suitable|intelligent|trustworthy|reliable)"
    r"|more likely to (commit|default|fail|reoffend|drop out|be aggressive)"
    r"|not (suitable|qualified|a good fit|reliable) (for|because|as)"
    r"|should (not )?be (hired|approved|denied|rejected|promoted|trusted)"
    r"|(those|these) people|all of (them|those)|by nature|inherently|naturally (better|worse)"
    r"|prone to|typical of|tend to be (lazy|violent|aggressive|dishonest)"
    r"|(don'?t|do not) belong)\b",
    re.IGNORECASE,
)


class BiasHeuristicDetector(Detector):
    """Flag a response that pairs a protected-group mention with loaded decision/stereotype language."""

    name = "bias_heuristic"
    axis = Axis.RESPONSIBILITY
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0
    informativeness = 0.6

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        text = ctx.response or ""
        protected = len(_PROTECTED.findall(text))
        loaded = len(_LOADED.findall(text))
        if protected == 0 or loaded == 0:
            return 0.0, {"bias": False, "protected": protected, "loaded": loaded}
        # Both present -> a biased judgement about a group. Multiple loaded markers compound.
        score = 1.0 - 0.35 ** min(loaded, 3)
        return score, {"bias": True, "protected": protected, "loaded": loaded}
