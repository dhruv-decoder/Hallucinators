"""Responsibility-axis detectors: is the response leaking data, or unsafe?

Today: a regex/heuristic PII detector (T0). Upgrade path: GLiNER zero-shot entity detection and
Presidio (T1) for recall on messy entities, and a safety/toxicity classifier (T1) plus a Llama-Guard
class model (T2) for unsafe content. See docs/PLAN.md section 8.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.base import Detector
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

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        text = ctx.response or ""
        found: dict[str, int] = {}
        for entity, pattern in _PATTERNS.items():
            matches = pattern.findall(text)
            if entity == "credit_card":
                matches = [m for m in matches if _luhn_ok(m)]
            if matches:
                found[entity] = len(matches)

        if not found:
            return 0.0, {"entities": {}, "note": "no PII patterns matched"}

        # Noisy-OR over the severities of the distinct entity types present.
        product = 1.0
        for entity in found:
            product *= 1.0 - _PII_SEVERITY.get(entity, 0.5)
        score = 1.0 - product
        return score, {"entities": found}
