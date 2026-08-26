"""Tests for the durable SQLite flight recorder."""

from __future__ import annotations

from controlplane.cascade.detectors.factory import build_cost_detectors, build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import PnlEntry, RequestContext
from controlplane.recorder.sqlite_store import SqliteRecorder


def _result(rid: str):
    engine = CascadeEngine(
        build_failure_detectors(use_hhem=False, use_presidio=False, use_judge=False), build_cost_detectors()
    )
    return engine.run(RequestContext(request_id=rid, response="Support is open 9am to 6pm."))


def test_records_and_verifies_chain(tmp_path) -> None:
    rec = SqliteRecorder(tmp_path / "cp.db")
    for i in range(3):
        rec.record(_result(f"r{i}"), PnlEntry(), policy_id="test")
    assert len(rec.receipts) == 3
    assert rec.verify_chain() is True


def test_persists_across_restart(tmp_path) -> None:
    path = tmp_path / "cp.db"
    rec = SqliteRecorder(path)
    rec.record(_result("r0"), PnlEntry(), policy_id="test")
    first_hash = rec.receipts[-1].hash_self

    # A fresh recorder on the same file reloads the chain and continues it.
    rec2 = SqliteRecorder(path)
    assert len(rec2.receipts) == 1
    assert rec2.verify_chain() is True
    r = rec2.record(_result("r1"), PnlEntry(), policy_id="test")
    assert r.hash_prev == first_hash  # chain continues across restart
    assert rec2.verify_chain() is True
