"""Model-backed responsibility detector: NER-based PII detection with Presidio + spaCy.

This is the realised upgrade of the regex PII heuristic. The regex detector (T0) catches structured
identifiers (cards, emails, SSNs) but is blind to free-text PII like people's names and locations.
Presidio runs a statistical NER model (spaCy) plus its own recognisers, so it flags "Sarah Chen from
Mumbai" that the regex cannot see.

It is an optional detector: it requires the ``[ml]`` extra and a one-time spaCy model download
(``python -m spacy download en_core_web_sm``). The core engine and demos run without it; enable it by
adding it to the detector list. Because PII screening is a mandatory first-pass gate rather than a
"maybe" check, it runs at T0 (always on) -- it is heavier than the regex heuristic (tens of ms), which is
the honest trade for catching free-text identifiers.
"""

from __future__ import annotations

from functools import lru_cache

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

# Presidio entity types we treat as PII, with a severity in [0, 1]. Types not listed (e.g. URL,
# DATE_TIME) are ignored because they are noisy and not, on their own, personal identifiers.
_ENTITY_SEVERITY = {
    "CREDIT_CARD": 0.95,
    "US_SSN": 0.95,
    "IBAN_CODE": 0.95,
    "US_BANK_NUMBER": 0.9,
    "US_PASSPORT": 0.9,
    "US_DRIVER_LICENSE": 0.85,
    "EMAIL_ADDRESS": 0.6,
    "PHONE_NUMBER": 0.6,
    "IP_ADDRESS": 0.45,
    "PERSON": 0.5,
    "LOCATION": 0.45,
    "NRP": 0.5,  # nationality / religious / political group
    "MEDICAL_LICENSE": 0.8,
}
_MIN_CONFIDENCE = 0.5


@lru_cache(maxsize=1)
def _get_analyzer():
    """Build and cache the Presidio analyzer configured for the small spaCy model.

    Construction loads a spaCy model and is relatively expensive, so it is cached process-wide. Raises a
    clear error if the optional dependencies are missing.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError as exc:  # pragma: no cover - exercised only without the [ml] extra
        raise ImportError(
            "PresidioPiiDetector needs the '[ml]' extra. Install with: pip install -e '.[ml]' "
            "and then: python -m spacy download en_core_web_sm"
        ) from exc

    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])


class PresidioPiiDetector(Detector):
    """Detect free-text and structured PII in a response using Presidio's NER-backed recognisers."""

    name = "presidio_pii"
    axis = Axis.RESPONSIBILITY
    tier = Tier.T0
    est_cost_usd = 0.0  # local inference: compute, not dollars
    est_latency_ms = 30.0
    informativeness = 0.8

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        text = ctx.response or ""
        if not text.strip():
            return 0.0, {"entities": {}, "note": "empty response"}

        results = _get_analyzer().analyze(text=text, language="en")
        found: dict[str, int] = {}
        contributions: list[float] = []
        for r in results:
            if r.score < _MIN_CONFIDENCE:
                continue
            severity = _ENTITY_SEVERITY.get(r.entity_type)
            if severity is None:
                continue
            found[r.entity_type] = found.get(r.entity_type, 0) + 1
            contributions.append(severity * min(r.score, 1.0))

        if not contributions:
            return 0.0, {"entities": {}, "note": "no PII entities above threshold"}

        # Noisy-OR over per-entity contributions, so multiple distinct leaks compound.
        product = 1.0
        for c in contributions:
            product *= 1.0 - c
        return 1.0 - product, {"entities": found}
