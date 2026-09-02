"""Recognise when a response *declines* to answer, so groundedness never punishes the safe behaviour.

A groundedness check asks "is this claim supported by the source?". A refusal or an "I don't have that
information" makes **no claim at all**, so there is nothing to ground -- yet both a lexical-overlap heuristic
and an NLI cross-encoder score it as unsupported, because the sentence shares no content with the source and
is not entailed by it. That turns the single most desirable model behaviour (abstaining instead of making
something up) into the highest-risk score on the performance axis, and the proxy then "repairs" a correct
refusal by overwriting it with raw source text.

So before a groundedness detector scores a response, we strip the clauses that assert nothing:

- If **nothing substantive remains**, the detector abstains (score 0, ``abstained`` in the receipt detail).
  Declining to answer is not a hallucination.
- If some substantive claim remains ("I don't have a phone number for that, but the refund window is 30
  days"), only that claim is scored -- the part that can actually be right or wrong.

This is deliberately conservative: only explicit, well-known abstention phrasing counts, so a confident
wrong answer is never mistaken for a refusal. It is a precision fix, and it cannot hide a real failure --
a response that states a fact still gets that fact checked.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.text import fold_typography

#: Sentence-level abstention/refusal markers. Each pattern must be an explicit statement that the model is
#: *not* answering -- never mere hedging ("it may be around 30 days" still asserts something and is scored).
_ABSTAIN = re.compile(
    r"("
    r"i(?:'m| am)? ?(?:so |very )?sorry"
    r"|i (?:can(?:'|no)?t|cannot|am unable to|'m unable to|won'?t be able to)"
    r" (?:help|assist|comply|provide|share|give|answer|do that)"
    r"|i (?:do not|don'?t) (?:have|know|see|find)"
    r"|i (?:do not|don'?t) have (?:access|that|the|any|enough)"
    r"|(?:is|are|was|were) not (?:mentioned|specified|provided|included|listed|stated|given|available)"
    r"|(?:that|this|it) (?:information |detail |number )?(?:is|'s| is) not"
    r" (?:in|available|included|provided|specified|mentioned)"
    r"|(?:is|are|was|were) not (?:in|included in|mentioned in|specified in|provided in|part of)"
    r" the (?:source|context|document|information|provided)"
    r"|(?:no|not any) (?:information|details?|record|data) (?:is |are |was )?(?:available|provided|given|in the source)"
    r"|the (?:source|context|document|information) (?:provided )?(?:does|doesn'?t|does not)"
    r" (?:not )?(?:contain|mention|include|specify|state)"
    r"|isn'?t (?:in|available in|mentioned in|specified in) the"
    r"|i'?m not able to"
    r"|i cannot (?:provide|share|disclose|confirm)"
    r"|unable to (?:provide|share|confirm|verify)"
    r"|please (?:contact|reach out to|refer to)"
    r")",
    re.IGNORECASE,
)

#: Split on sentence boundaries, list-item boundaries, and the conjunctions that join an answer to a
#: disclaimer. A model very often packs both into one sentence -- "You have 30 days to return it, and the
#: restocking fee is not mentioned in the policy" -- where the first clause is a checkable claim and the
#: second asserts nothing. Splitting only on sentences leaves them fused, so the disclaimer drags the whole
#: sentence through groundedness scoring and a correct answer is flagged as unsupported.
_SPLIT = re.compile(
    r"(?<=[.!?])\s+"          # sentence end
    r"|\n+"                   # line or list-item break
    r"|\s*;\s*"              # semicolon, the usual claim/disclaimer joint
    r"|,?\s+(?:but|although|though|however)\s+"   # contrastive clause
    r"|,\s+(?:and|while)\s+(?=[^,]*\b(?:not|no|isn'?t|aren'?t|don'?t|doesn'?t|unavailable)\b)",
    re.IGNORECASE,
)

#: A residue this short after stripping abstention clauses is punctuation/filler, not a claim.
_MIN_SUBSTANTIVE_WORDS = 4


def split_abstention(text: str) -> tuple[str, list[str]]:
    """Return ``(substantive_text, abstention_clauses)`` for ``text``.

    ``substantive_text`` is everything that actually asserts something and can therefore be checked for
    groundedness. It is empty when the response is a pure refusal.
    """
    if not text or not text.strip():
        return "", []
    # Models write "I'm sorry" and "don't" with curly apostrophes, so an ASCII-only pattern silently never
    # matches -- which is exactly how a correct refusal ended up scored as a maximal groundedness failure.
    text = fold_typography(text)
    substantive: list[str] = []
    abstained: list[str] = []
    for part in _SPLIT.split(text):
        clean = part.strip()
        if not clean:
            continue
        (abstained if _ABSTAIN.search(clean) else substantive).append(clean)
    if not abstained:
        # Nothing was declined, so there is nothing to separate. Return the response untouched rather than
        # a version reassembled from the split, which would drop the punctuation the detectors read.
        return text.strip(), []
    joined = " ".join(substantive).strip()
    # A stub like "However:" or a bare bullet marker is not a claim.
    if len(re.findall(r"[A-Za-z0-9]+", joined)) < _MIN_SUBSTANTIVE_WORDS:
        return "", abstained + ([joined] if joined else [])
    return joined, abstained


def is_abstention(text: str) -> bool:
    """True when the response makes no checkable claim at all (a pure refusal / "I don't know")."""
    substantive, abstained = split_abstention(text)
    return bool(abstained) and not substantive
