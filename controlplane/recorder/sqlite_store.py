"""A SQLite-backed flight recorder -- durable, queryable persistence for the audit log.

The reference ``JsonlRecorder`` keeps receipts in memory (+ an optional JSONL mirror), which is fine for a
demo but resets on restart. ``SqliteRecorder`` persists every receipt to a SQLite table and reloads them on
start, so the tamper-evident hash chain survives restarts -- the honest first step toward an enterprise audit
store (SQLite -> Postgres is a driver swap). It implements the same ``record`` / ``receipts`` / ``verify_chain``
interface, so the engine, proxy, and UI use it unchanged.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from controlplane.core.types import CascadeResult, PnlEntry, VoIReceipt
from controlplane.recorder.receipt import build_receipt, compute_hash


class SqliteRecorder:
    """Append-only, hash-chained receipt store backed by SQLite (with an in-memory mirror for fast reads)."""

    def __init__(self, path: str | Path = "controlplane.db") -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS receipts "
            "(seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, ts TEXT, "
            "hash_prev TEXT, hash_self TEXT, body TEXT)"
        )
        self._conn.commit()
        # Reload existing receipts so the chain continues across restarts.
        self.receipts: list[VoIReceipt] = [
            VoIReceipt.model_validate_json(row[0])
            for row in self._conn.execute("SELECT body FROM receipts ORDER BY seq")
        ]
        self._last_hash = self.receipts[-1].hash_self if self.receipts else ""

    def record(
        self, result: CascadeResult, pnl: PnlEntry, policy_id: str, repaired_output: str | None = None
    ) -> VoIReceipt:
        receipt = build_receipt(
            result, pnl, policy_id, hash_prev=self._last_hash, repaired_output=repaired_output
        )
        self._conn.execute(
            "INSERT INTO receipts (request_id, ts, hash_prev, hash_self, body) VALUES (?,?,?,?,?)",
            (receipt.request_id, receipt.ts.isoformat(), receipt.hash_prev, receipt.hash_self,
             json.dumps(receipt.model_dump(mode="json"))),
        )
        self._conn.commit()
        self.receipts.append(receipt)
        self._last_hash = receipt.hash_self
        return receipt

    def verify_chain(self) -> bool:
        prev = ""
        for receipt in self.receipts:
            if receipt.hash_prev != prev or compute_hash(receipt) != receipt.hash_self:
                return False
            prev = receipt.hash_self
        return True
