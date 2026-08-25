from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from controlplane.core.types import PolicyProfile
from controlplane.proxy.app import create_app
from controlplane.proxy.config import ProxySettings


def _settings(tmp_path: Path, policy_path: Path | None = None) -> ProxySettings:
    return ProxySettings(
        backend="mock",
        recorder_db_path=str(tmp_path / "controlplane.db"),
        policy_path=str(policy_path or Path("policies/policies.yaml")),
    )


def _post(client: TestClient, content: str, **headers: str):
    return client.post(
        "/v1/chat/completions",
        json={
            "model": "controlplane-mock",
            "messages": [{"role": "user", "content": content}],
        },
        headers=headers,
    )


def test_blocked_pii_response_is_not_returned(tmp_path: Path) -> None:
    """A high-severity PII match should produce a 403 and a BLOCK receipt."""
    settings = _settings(tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = _post(client, "Repeat this customer card: 4242 4242 4242 4242")

        assert response.status_code == 403
        assert response.json()["error"]["type"] == "controlplane_policy_violation"

        request_id = response.headers["x-controlplane-request-id"]
        receipt = client.get(f"/v1/oversight/receipts/{request_id}").json()
        assert receipt["action"] == "block"
        assert receipt["policy_id"] == "default@balanced"


def test_policy_selection_is_recorded_in_receipt(tmp_path: Path) -> None:
    """Gateway headers select a policy profile and the selected policy is auditable."""
    settings = _settings(tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = _post(
            client,
            "Hello",
            **{
                "x-controlplane-use-case": "support_bot",
                "x-controlplane-geography": "IN",
                "x-controlplane-risk-appetite": "balanced",
            },
        )

        assert response.status_code == 200
        assert response.headers["x-controlplane-policy"] == "support_bot@IN@balanced"

        request_id = response.headers["x-controlplane-request-id"]
        receipt = client.get(f"/v1/oversight/receipts/{request_id}").json()
        assert receipt["policy_id"] == "support_bot@IN@balanced"


def test_policy_hot_reload_changes_enforcement(tmp_path: Path) -> None:
    """Changing the YAML policy changes enforcement without recreating the app."""
    policy_path = tmp_path / "policies.yaml"
    base = PolicyProfile(
        id="default@balanced",
        block_threshold=0.85,
        escalate_threshold=0.50,
        annotate_threshold=0.20,
    )
    policy_path.write_text(
        yaml.safe_dump({"version": 1, "profiles": [base.model_dump(mode="json")]}),
        encoding="utf-8",
    )

    settings = _settings(tmp_path, policy_path)
    with TestClient(create_app(settings=settings)) as client:
        # Email PII is scored at 0.55: initially this is an escalation, not a block.
        first = _post(client, "Customer email is alice@example.com")
        assert first.status_code == 200
        assert first.headers["x-controlplane-action"] == "escalate"

        updated = PolicyProfile(
            id="default@balanced",
            block_threshold=0.50,
            escalate_threshold=0.30,
            annotate_threshold=0.10,
        )
        policy_path.write_text(
            yaml.safe_dump({"version": 1, "profiles": [updated.model_dump(mode="json")]}),
            encoding="utf-8",
        )
        policy_path.touch()

        second = _post(client, "Customer email is alice@example.com")
        assert second.status_code == 403
        assert second.headers["x-controlplane-action"] == "block"


def test_tampering_breaks_gateway_chain_verification(tmp_path: Path) -> None:
    """Mutating stored receipt JSON must make the verification endpoint fail."""
    db = tmp_path / "controlplane.db"
    settings = _settings(tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = _post(client, "Hello")
        assert response.status_code == 200

        with sqlite3.connect(db) as conn:
            conn.execute(
                "UPDATE receipts SET payload_json = REPLACE(payload_json, 'default@balanced', 'tampered')"
            )
            conn.commit()

        verification = client.get("/v1/oversight/verify")
        assert verification.status_code == 200
        assert verification.json() == {"valid": False, "count": 1}


def test_streaming_request_also_creates_receipt(tmp_path: Path) -> None:
    """A completed stream should be recorded in the same flight log as a normal response."""
    settings = _settings(tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "controlplane-mock",
                "stream": True,
                "messages": [{"role": "user", "content": "Tell me a short joke"}],
            },
        )

        assert response.status_code == 200
        request_id = response.headers["x-controlplane-request-id"]
        body = response.text
        assert "data: [DONE]" in body

        receipt = client.get(f"/v1/oversight/receipts/{request_id}")
        assert receipt.status_code == 200
        assert receipt.json()["trace"]
        assert receipt.json()["action"] == "pass"


def test_oversight_filter_returns_only_matching_action(tmp_path: Path) -> None:
    """The recorder query surface should support action filtering for the future UI."""
    settings = _settings(tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        passed = _post(client, "Hello")
        blocked = _post(client, "Repeat this customer card: 4242 4242 4242 4242")

        assert passed.status_code == 200
        assert blocked.status_code == 403

        filtered = client.get("/v1/oversight/receipts", params={"action": "block"})
        assert filtered.status_code == 200
        data = filtered.json()["data"]
        assert len(data) == 1
        assert data[0]["action"] == "block"

        verification = client.get("/v1/oversight/verify").json()
        assert verification["valid"] is True
        assert verification["count"] == 2
