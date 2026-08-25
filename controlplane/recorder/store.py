"""Append-only SQLite flight recorder for VoI receipts.

P2 owns the durable store and query surface.  ``JsonlRecorder`` remains available for backwards
compatibility with the original demos/tests; production-facing code should use ``SQLiteFlightRecorder``.

The SQLite recorder stores the canonical receipt JSON plus indexed metadata used by the dashboard.
Each append runs inside a ``BEGIN IMMEDIATE`` transaction so reading the current chain head and
inserting the next receipt are serialized.  This preserves the SHA-256 chain under concurrent writers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from controlplane.core.types import Action, CascadeResult, PnlEntry, VoIReceipt
from controlplane.recorder.receipt import build_receipt, compute_hash


class JsonlRecorder:
    """Append-only, hash-chained receipt store backed by an in-memory list and optional JSONL."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.receipts: list[VoIReceipt] = []
        self._last_hash: str = ""
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")

    def record(
        self,
        result: CascadeResult,
        pnl: PnlEntry,
        policy_id: str,
        repaired_output: str | None = None,
    ) -> VoIReceipt:
        receipt = build_receipt(
            result, pnl, policy_id, hash_prev=self._last_hash, repaired_output=repaired_output
        )
        self._append(receipt)
        return receipt

    def _append(self, receipt: VoIReceipt) -> None:
        self.receipts.append(receipt)
        self._last_hash = receipt.hash_self
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt.model_dump(mode="json")) + "\n")

    def verify_chain(self) -> bool:
        prev = ""
        for receipt in self.receipts:
            if receipt.hash_prev != prev:
                return False
            if compute_hash(receipt) != receipt.hash_self:
                return False
            prev = receipt.hash_self
        return True


class SQLiteFlightRecorder:
    """Durable append-only receipt store with a hash chain and query helpers.

    Parameters
    ----------
    path:
        SQLite database path.  ``":memory:"`` is useful in unit tests.
    """

    def __init__(self, path: str | Path = "controlplane.db") -> None:
        self.path = str(path)
        self._lock = Lock()
        self._uri = self.path == ":memory:"
        if not self._uri:
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0, uri=self._uri)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    ts TEXT NOT NULL,
                    use_case TEXT NOT NULL,
                    action TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    cost_saved_usd REAL NOT NULL,
                    safety_spend_usd REAL NOT NULL,
                    net_usd REAL NOT NULL,
                    hash_prev TEXT NOT NULL,
                    hash_self TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_ts ON receipts(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_action ON receipts(action)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_use_case ON receipts(use_case)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_receipts_policy ON receipts(policy_id)")
            conn.commit()

    @staticmethod
    def _row_to_receipt(row: sqlite3.Row) -> VoIReceipt:
        payload = json.loads(row["payload_json"])
        return VoIReceipt.model_validate(payload)

    def record(
        self,
        result: CascadeResult,
        pnl: PnlEntry,
        policy_id: str,
        repaired_output: str | None = None,
    ) -> VoIReceipt:
        """Build and persist one receipt atomically, chaining it to the latest receipt."""
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT hash_self FROM receipts ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                hash_prev = str(row["hash_self"]) if row else ""
                receipt = build_receipt(
                    result,
                    pnl,
                    policy_id,
                    hash_prev=hash_prev,
                    repaired_output=repaired_output,
                )
                payload = receipt.model_dump(mode="json")
                conn.execute(
                    """
                    INSERT INTO receipts (
                        request_id, ts, use_case, action, policy_id,
                        cost_saved_usd, safety_spend_usd, net_usd,
                        hash_prev, hash_self, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.request_id,
                        receipt.ts.isoformat(),
                        receipt.use_case,
                        receipt.action.value,
                        receipt.policy_id,
                        receipt.pnl.cost_saved_usd,
                        receipt.pnl.safety_spend_usd,
                        receipt.pnl.net_usd,
                        receipt.hash_prev,
                        receipt.hash_self,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    ),
                )
                conn.commit()
                return receipt

    def get(self, request_id: str) -> VoIReceipt | None:
        """Return a receipt by request id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM receipts WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return self._row_to_receipt(row) if row else None

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        action: Action | str | None = None,
        use_case: str | None = None,
        policy_id: str | None = None,
    ) -> list[VoIReceipt]:
        """Return newest-first receipts with optional indexed filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if action is not None:
            clauses.append("action = ?")
            params.append(action.value if isinstance(action, Action) else str(action))
        if use_case is not None:
            clauses.append("use_case = ?")
            params.append(use_case)
        if policy_id is not None:
            clauses.append("policy_id = ?")
            params.append(policy_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        params.extend([limit, offset])
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM receipts {where} ORDER BY seq DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [self._row_to_receipt(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM receipts").fetchone()
        return int(row["n"])

    def verify_chain(self) -> bool:
        """Recompute and verify every receipt and predecessor link from the durable log."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM receipts ORDER BY seq ASC"
            ).fetchall()
        prev = ""
        for row in rows:
            receipt = self._row_to_receipt(row)
            if receipt.hash_prev != prev:
                return False
            if compute_hash(receipt) != receipt.hash_self:
                return False
            prev = receipt.hash_self
        return True

    def close(self) -> None:
        """Compatibility no-op; connections are opened per operation."""
        return None


Recorder = SQLiteFlightRecorder
