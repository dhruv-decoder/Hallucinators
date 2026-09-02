"""Build a VoI receipt from a cascade result and chain it by hash.

The hash chain makes the flight log tamper-evident: each receipt's ``hash_self`` is the SHA-256 of its
own canonical JSON (with ``hash_self`` blanked) plus the previous receipt's ``hash_self``. Changing any
past receipt changes its hash, which breaks every subsequent link -- so tampering is detectable even
though the store itself is an ordinary file. This is "tamper-evident", not "immutable"; we say exactly
what it is.
"""

from __future__ import annotations

import hashlib
import json

from controlplane.core.types import CascadeResult, PnlEntry, Transcript, VoIReceipt

#: Cap on any single stored text field. Receipts are an audit trail, not a content archive; a very long
#: response would bloat the chain and the SSE feed without making the decision any more reviewable.
_MAX_CHARS = 1200


def _safe(text: str) -> tuple[str, dict[str, int], bool]:
    """Redact identifiers out of ``text`` and cap its length. Returns ``(text, redacted_counts, truncated)``."""
    from controlplane.cascade.detectors.responsibility import redact_pii

    clean, counts = redact_pii(text or "")
    truncated = len(clean) > _MAX_CHARS
    return (clean[:_MAX_CHARS] + "…" if truncated else clean), counts, truncated


def build_transcript(result: CascadeResult, delivered: str | None = None) -> Transcript:
    """Build the redacted, length-capped transcript that goes into the receipt.

    Redaction runs on everything -- prompt, candidate response, delivered text, and retrieved context --
    using the same patterns the PII detector scores with, so a leak the system just blocked is never
    written into the audit log in the clear.
    """
    prompt, p_counts, p_trunc = _safe(result.prompt)
    response, r_counts, r_trunc = _safe(result.response)
    delivered_text, d_counts, d_trunc = _safe(delivered if delivered is not None else result.response)
    context: list[str] = []
    c_counts: dict[str, int] = {}
    c_trunc = False
    for chunk in result.retrieved_context[:4]:
        text, counts, trunc = _safe(chunk)
        context.append(text)
        c_trunc = c_trunc or trunc
        for key, value in counts.items():
            c_counts[key] = c_counts.get(key, 0) + value

    redacted: dict[str, int] = {}
    for counts in (p_counts, r_counts, d_counts, c_counts):
        for key, value in counts.items():
            redacted[key] = redacted.get(key, 0) + value
    return Transcript(
        prompt=prompt,
        response=response,
        delivered=delivered_text,
        retrieved_context=context,
        model=result.model,
        redacted=redacted,
        truncated=p_trunc or r_trunc or d_trunc or c_trunc,
    )


def compute_hash(receipt: VoIReceipt) -> str:
    """SHA-256 over the receipt's canonical JSON (with ``hash_self`` blanked) plus ``hash_prev``.

    ``hash_prev`` is part of the hashed body, so the link to the previous receipt is itself protected.
    """
    body = receipt.model_dump(mode="json", exclude={"hash_self"})
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_receipt(
    result: CascadeResult,
    pnl: PnlEntry,
    policy_id: str,
    hash_prev: str = "",
    repaired_output: str | None = None,
) -> VoIReceipt:
    """Assemble a hash-chained receipt from the engine's result and the booked P&L."""
    receipt = VoIReceipt(
        request_id=result.request_id,
        use_case=result.use_case,
        transcript=build_transcript(result, delivered=repaired_output),
        signals=result.signals,
        cost_opportunities=result.cost_opportunities,
        per_axis=result.per_axis,
        expected_loss_before=result.expected_loss_before,
        expected_loss_after=result.expected_loss_after,
        stopping_reason=result.stopping_reason,
        action=result.action,
        repaired_output=repaired_output,
        pnl=pnl,
        trace=result.trace,
        policy_id=policy_id,
        hash_prev=hash_prev,
    )
    receipt.hash_self = compute_hash(receipt)
    return receipt
