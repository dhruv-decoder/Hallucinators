from __future__ import annotations

import time

from fastapi.testclient import TestClient

from controlplane.proxy.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(recorder_path=None, force_simulated=True))


def test_request_id_is_propagated_and_receipt_can_be_verified() -> None:
    client = _client()
    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Request-ID": "demo-correlation-123"},
        json={"model": "controlplane-sim", "messages": [{"role": "user", "content": "Hello"}]},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "demo-correlation-123"
    receipt = resp.json()["controlplane"]["receipt_id"]
    assert receipt == "demo-correlation-123"
    verified = client.get(f"/v1/oversight/receipts/{receipt}/verify")
    assert verified.status_code == 200
    assert verified.json()["receipt_valid"] is True
    assert verified.json()["chain_valid"] is True


def test_readiness_and_observability_are_live() -> None:
    client = _client()
    assert client.get("/readyz").json()["ready"] is True
    client.post(
        "/v1/chat/completions",
        json={"model": "controlplane-sim", "messages": [{"role": "user", "content": "Hello"}]},
    )
    data = client.get("/v1/oversight/observability").json()
    assert data["requests"] >= 1
    assert data["latency_ms"]["sample_count"] >= 1
    assert "config" in data
    assert data["config"]["max_concurrency"] >= 1


def test_runtime_probe_completes_and_reports_latency() -> None:
    client = _client()
    started = client.post("/v1/oversight/jobs/runtime-probe?n=12&concurrency=4").json()
    job_id = started["id"]
    for _ in range(100):
        snap = client.get(f"/v1/oversight/jobs/{job_id}").json()
        if snap["status"] != "running":
            break
        time.sleep(0.02)
    assert snap["status"] == "done"
    result = snap["result"]
    assert result["requests"] == 12
    assert result["concurrency"] == 4
    assert result["throughput_rps"] > 0
    assert result["latency_ms"]["p95"] >= result["latency_ms"]["p50"]

def test_runtime_probe_reports_overload_when_client_exceeds_capacity() -> None:
    client = _client()

    started = client.post(
        "/v1/oversight/jobs/runtime-probe?n=80&concurrency=64"
    )

    assert started.status_code == 200

    job_id = started.json()["id"]

    for _ in range(100):
        snap = client.get(
            f"/v1/oversight/jobs/{job_id}"
        ).json()

        if snap["status"] != "running":
            break

        time.sleep(0.02)

    assert snap["status"] == "done"

    result = snap["result"]

    assert result["requests"] == 80
    assert result["concurrency"] == 64
    assert "rejected_overload" in result
    assert result["rejected_overload"] >= 0
    assert result["accepted"] + result["rejected_overload"] + result["errors"] == result["requests"]
    assert result["throughput_rps"] > 0


def test_readyz_reports_configured_concurrency() -> None:
    client = _client()
    response = client.get("/readyz")

    assert response.status_code == 200

    data = response.json()

    assert data["ready"] is True