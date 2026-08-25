from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from controlplane.proxy.app import create_app
from controlplane.proxy.config import ProxySettings


def test_proxy_records_oversight_receipt(tmp_path: Path) -> None:
    settings = ProxySettings(
        backend="mock",
        recorder_db_path=str(tmp_path / "controlplane.db"),
        policy_path="policies/policies.yaml",
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "controlplane-mock",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        assert response.status_code == 200
        request_id = response.headers["x-controlplane-request-id"]
        assert response.headers["x-controlplane-action"] in {"pass", "annotate", "auto_repair", "escalate", "block"}

        receipt = client.get(f"/v1/oversight/receipts/{request_id}")
        assert receipt.status_code == 200
        assert receipt.json()["request_id"] == request_id

        verify = client.get("/v1/oversight/verify")
        assert verify.status_code == 200
        assert verify.json()["valid"] is True
        assert verify.json()["count"] == 1
