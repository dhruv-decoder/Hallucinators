from __future__ import annotations

from pathlib import Path

from controlplane.core.types import Action, CascadeResult, PnlEntry
from controlplane.recorder import SQLiteFlightRecorder


def _result(request_id: str, action: Action = Action.PASS) -> CascadeResult:
    return CascadeResult(request_id=request_id, use_case="support_bot", action=action)


def test_sqlite_recorder_persists_and_reopens(tmp_path: Path) -> None:
    db = tmp_path / "flight.db"
    recorder = SQLiteFlightRecorder(db)
    receipt = recorder.record(_result("req-1"), PnlEntry(cost_saved_usd=1.0), "support_bot@IN@balanced")
    assert recorder.count() == 1
    assert recorder.verify_chain()

    reopened = SQLiteFlightRecorder(db)
    stored = reopened.get("req-1")
    assert stored is not None
    assert stored.hash_self == receipt.hash_self
    assert reopened.verify_chain()


def test_sqlite_recorder_chains_and_filters(tmp_path: Path) -> None:
    recorder = SQLiteFlightRecorder(tmp_path / "flight.db")
    first = recorder.record(_result("req-1"), PnlEntry(), "default@balanced")
    second = recorder.record(_result("req-2", Action.BLOCK), PnlEntry(safety_spend_usd=0.1), "default@balanced")

    assert second.hash_prev == first.hash_self
    assert recorder.verify_chain()
    blocked = recorder.list(action=Action.BLOCK)
    assert [r.request_id for r in blocked] == ["req-2"]

    assert recorder.get("missing") is None


def test_sqlite_recorder_detects_tampering(tmp_path: Path) -> None:
    db = tmp_path / "flight.db"
    recorder = SQLiteFlightRecorder(db)
    recorder.record(_result("req-1"), PnlEntry(), "default@balanced")
    recorder.record(_result("req-2"), PnlEntry(), "default@balanced")

    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE receipts SET payload_json = REPLACE(payload_json, 'default', 'tampered') WHERE request_id = 'req-1'")
        conn.commit()

    assert not recorder.verify_chain()


def test_sqlite_recorder_serializes_concurrent_appends(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    recorder = SQLiteFlightRecorder(tmp_path / "flight.db")

    def write(i: int) -> str:
        return recorder.record(_result(f"req-{i}"), PnlEntry(), "default@balanced").hash_self

    with ThreadPoolExecutor(max_workers=8) as pool:
        hashes = list(pool.map(write, range(20)))

    assert len(hashes) == 20
    assert recorder.count() == 20
    assert recorder.verify_chain()
