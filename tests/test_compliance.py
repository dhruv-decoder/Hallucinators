"""Tests for the compliance evidence pack."""

from __future__ import annotations

from fastapi.testclient import TestClient

from controlplane.compliance import generate_pack, render_markdown
from controlplane.proxy.app import create_app


def test_pack_covers_all_frameworks() -> None:
    client = TestClient(create_app(recorder_path=None, force_simulated=True))
    client.post("/v1/oversight/simulate")
    pack = client.get("/v1/oversight/compliance").json()
    frameworks = {c["framework"] for c in pack["controls"]}
    assert {"EU AI Act", "ISO/IEC 42001", "NIST AI RMF"} <= frameworks
    assert pack["decisions"] > 0
    assert pack["chain_valid"] is True
    # Human-oversight and record-keeping controls should be evidenced after real traffic.
    statuses = {c["control"]: c["status"] for c in pack["controls"]}
    assert any("Art. 12" in k and v == "evidenced" for k, v in statuses.items())


def test_render_markdown_has_table_and_disclaimer() -> None:
    pack = generate_pack([], chain_valid=True, policy_id="test@balanced")
    md = render_markdown(pack)
    assert "# ControlPlane — Compliance Evidence Pack" in md
    assert "EU AI Act" in md and "NIST AI RMF" in md
    assert "evidence aid" in md  # the disclaimer


def test_compliance_markdown_endpoint_downloads() -> None:
    client = TestClient(create_app(recorder_path=None, force_simulated=True))
    client.post("/v1/oversight/simulate")
    resp = client.get("/v1/oversight/compliance.md")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "Compliance Evidence Pack" in resp.text
