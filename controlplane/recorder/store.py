"""A minimal append-only receipt store.

This is a reference implementation good enough to run the pipeline and the demo end to end: it keeps
receipts in memory, maintains the hash chain, and optionally mirrors each receipt to a JSONL file. P2
replaces it with the SQLite-backed flight recorder (with a query API for the UI) described in
docs/PLAN.md and docs/WORKPLAN.md; the ``append`` / ``verify_chain`` interface stays the same.
"""

from __future__ import annotations

import json
from pathlib import Path

from controlplane.core.types import CascadeResult, PnlEntry, VoIReceipt
from controlplane.recorder.receipt import build_receipt, compute_hash


class JsonlRecorder:
    """Append-only, hash-chained receipt store backed by an in-memory list and an optional JSONL file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.receipts: list[VoIReceipt] = []
        self._last_hash: str = ""
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")  # start a fresh log for a fresh run

    def record(
        self,
        result: CascadeResult,
        pnl: PnlEntry,
        policy_id: str,
        repaired_output: str | None = None,
    ) -> VoIReceipt:
        """Build a receipt chained onto the previous one, store it, and return it."""
        receipt = build_receipt(
            result, pnl, policy_id, hash_prev=self._last_hash, repaired_output=repaired_output
        )
        self._append(receipt)
        return receipt

    def _append(self, receipt: VoIReceipt) -> None:
        self.receipts.append(receipt)
        self._last_hash = receipt.hash_self
        if self.path is not None:
            with self.path.open("a") as fh:
                fh.write(json.dumps(receipt.model_dump(mode="json")) + "\n")

    def verify_chain(self) -> bool:
        """Return True if every receipt's hash matches its contents and links to its predecessor."""
        prev = ""
        for receipt in self.receipts:
            if receipt.hash_prev != prev:
                return False
            if compute_hash(receipt) != receipt.hash_self:
                return False
            prev = receipt.hash_self
        return True
