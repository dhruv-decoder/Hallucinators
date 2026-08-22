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

from controlplane.core.types import CascadeResult, PnlEntry, VoIReceipt


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
