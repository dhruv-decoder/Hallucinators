"""Responsibility-axis detectors: is the response leaking data, or unsafe?

Today: a regex/heuristic PII detector (T0). Upgrade path: GLiNER zero-shot entity detection and
Presidio (T1) for recall on messy entities, and a safety/toxicity classifier (T1) plus a Llama-Guard
class model (T2) for unsafe content.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.base import Detector
from controlplane.cascade.detectors.text import fold_typography
from controlplane.core.types import Axis, RequestContext, Tier

# Per-entity severity in [0, 1]. Financial and government identifiers are treated as higher stakes than
# a bare email or phone number. These are deliberate, documented weights, not tuned on any hidden data.
_PII_SEVERITY = {
    "credit_card": 0.95,
    "us_ssn": 0.95,
    "aadhaar": 0.9,
    "email": 0.55,
    "phone": 0.55,
    "ip_address": 0.4,
}

_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)\d{3}[\s-]?\d{4}\b"),
    "us_ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    # Candidate card numbers: 13-19 digits with optional spaces/dashes. Confirmed with a Luhn check.
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}

#: Resolution order when patterns overlap: most specific / highest severity first. A Luhn-valid 16-digit
#: card also matches the 12-digit Aadhaar pattern on its leading groups, so without an explicit precedence
#: the same leak gets reported under the wrong entity name.
_PRECEDENCE = ["credit_card", "us_ssn", "aadhaar", "email", "phone", "ip_address"]
_ORDERED = [e for e in _PRECEDENCE if e in _PATTERNS] + [e for e in _PATTERNS if e not in _PRECEDENCE]

#: Model output is typographic, not ASCII: a markdown-styled card number comes back with narrow no-break
#: spaces between the digit groups. A literal " " in the card pattern does not match those, so the card
#: pattern silently missed the leak while the looser Aadhaar pattern (``\s`` *is* Unicode-aware) still
#: matched -- reporting a real Visa number as an Aadhaar number. Folding is 1:1, so match offsets computed
#: on the folded text still index the original correctly and redaction cuts exactly the right characters.


def _luhn_ok(number: str) -> bool:
    """Return True if the digit string passes the Luhn checksum (used by real card numbers)."""
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def detect_pii(text: str) -> dict[str, int]:
    """Return ``{entity_type: count}`` for the identifiers present in ``text``.

    Overlapping patterns are resolved most-specific-first so an entity is reported under the *right* name:
    a 16-digit Luhn-valid card also matches the 12-digit Aadhaar pattern on its first three groups, and
    reporting "aadhaar" for a Visa number makes the evidence in the receipt (and the block notice a user
    sees) plainly wrong. Once a span is claimed by a higher-precedence entity, later patterns cannot
    re-claim the same digits.
    """
    return {entity: len(spans) for entity, spans in _pii_spans(text).items()}


def _pii_spans(text: str) -> dict[str, list[tuple[int, int]]]:
    """Map each entity type to the character spans it owns, resolving overlaps by ``_PRECEDENCE``."""
    spans: dict[str, list[tuple[int, int]]] = {}
    claimed: list[tuple[int, int]] = []
    folded = fold_typography(text)  # same length as ``text``, so spans index either string correctly
    for entity in _ORDERED:
        for match in _PATTERNS[entity].finditer(folded):
            if entity == "credit_card" and not _luhn_ok(match.group(0)):
                continue  # not a real card number -> not a card leak
            start, end = match.span()
            while end > start and folded[end - 1] in " -":
                end -= 1  # the digit-run pattern can trail a separator; keep it out of the redaction
            if any(start < c_end and c_start < end for c_start, c_end in claimed):
                continue  # already attributed to a more specific entity
            claimed.append((start, end))
            spans.setdefault(entity, []).append((start, end))
    return spans


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """Replace detected PII spans with a typed placeholder, returning the redacted text and the counts.

    Uses the same span resolution as :func:`detect_pii`, so what the detector *flags* and what the proxy
    *redacts* can never drift apart -- and neither can the entity *names*: a leaked card becomes
    ``[REDACTED_CREDIT_CARD]``, never ``[REDACTED_AADHAAR]`` just because the Aadhaar pattern also matched
    its leading digits. The raw value never survives into the forwarded response or the audit log.
    Returns ``(redacted, counts)`` where ``counts`` maps entity type -> number redacted.
    """
    spans = _pii_spans(text)
    flat = sorted(
        ((start, end, entity) for entity, ss in spans.items() for start, end in ss),
        reverse=True,  # replace right-to-left so earlier offsets stay valid
    )
    redacted = text
    for start, end, entity in flat:
        redacted = f"{redacted[:start]}[REDACTED_{entity.upper()}]{redacted[end:]}"
    return redacted, {entity: len(ss) for entity, ss in spans.items()}


class RegexPiiDetector(Detector):
    """Detect personal / sensitive identifiers being emitted in a response.

    Emits a risk score combining the severities of all entity types found (via noisy-OR, so multiple
    distinct leaks compound). The receipt records entity *types* and counts, never the raw values -- we
    do not want the audit log to become a second copy of the leaked data.
    """

    name = "regex_pii"
    axis = Axis.RESPONSIBILITY
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0
    informativeness = 0.6
    construct = "pii"  # pattern-based identifier detection; Presidio is the NER-backed rival estimate

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        text = ctx.response or ""
        found = detect_pii(text)

        if not found:
            return 0.0, {"entities": {}, "note": "no PII patterns matched"}

        # Noisy-OR over the severities of the distinct entity types present.
        product = 1.0
        for entity in found:
            product *= 1.0 - _PII_SEVERITY.get(entity, 0.5)
        score = 1.0 - product
        return score, {"entities": found}
