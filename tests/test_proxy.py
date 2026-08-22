"""Tests for The Tower -- the OpenAI-compatible proxy and its oversight API.

These exercise the inline pipeline end to end (upstream -> cascade -> action -> receipt) through real HTTP
calls, so they cover the schema contract, each action path, the streaming mid-stream abort, and the
oversight endpoints the dashboard depends on. Everything runs against the offline simulated upstream.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from controlplane.cascade.detectors.responsibility import redact_pii
from controlplane.proxy.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(recorder_path=None, force_simulated=True))


def _chat(client: TestClient, prompt: str, model: str = "gpt-4o", use_case: str | None = None) -> dict:
    return client.post(
        "/v1/chat/completions",
        json={
            "model": model,
            "use_case": use_case,
            "messages": [{"role": "user", "content": prompt}],
        },
    ).json()


def test_response_is_openai_shaped_with_oversight_block(client: TestClient) -> None:
    r = _chat(client, "What are your customer support hours?")
    assert r["object"] == "chat.completion"
    assert r["choices"][0]["message"]["role"] == "assistant"
    assert "usage" in r
    cp = r["controlplane"]
    assert cp["action"] == "pass"
    assert cp["modified"] is False
    assert set(cp["per_axis_p_fail"]) == {"performance", "responsibility"}


def test_clean_answer_passes_unchanged(client: TestClient) -> None:
    r = _chat(client, "Where can I download the app?")
    assert r["controlplane"]["action"] == "pass"
    assert "App Store" in r["choices"][0]["message"]["content"]


def test_ungrounded_answer_is_auto_repaired_from_context(client: TestClient) -> None:
    r = _chat(client, "What is the refund window?")
    cp = r["controlplane"]
    assert cp["action"] == "auto_repair"
    assert cp["modified"] is True
    # The delivered answer is the grounded fact, not the confident 180-day hallucination.
    text = r["choices"][0]["message"]["content"]
    assert "30 days" in text
    assert "180" not in text


def test_pii_leak_is_blocked_and_values_never_forwarded(client: TestClient) -> None:
    r = _chat(client, "Can you share the customer's payment details?", model="gpt-4o-mini")
    cp = r["controlplane"]
    assert cp["action"] == "block"
    text = r["choices"][0]["message"]["content"]
    assert "4111" not in text and "jane.doe@acme.com" not in text
    assert cp["per_axis_p_fail"]["responsibility"] >= 0.85


def test_coupled_risk_lights_two_axes_and_escalates(client: TestClient) -> None:
    # A fabricated detail about a named person is both a hallucination and a privacy leak (brief A2).
    r = _chat(client, "Who is my account manager and how do I reach them?")
    cp = r["controlplane"]
    assert cp["action"] == "escalate"
    assert cp["per_axis_p_fail"]["performance"] > 0.5
    assert cp["per_axis_p_fail"]["responsibility"] > 0.2


def test_streaming_abort_holds_back_pii_digits(client: TestClient) -> None:
    content = ""
    oversight = None
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "Can you share the customer's payment details?"}],
        },
    ) as resp:
        for line in resp.iter_lines():
            if not line.startswith("data: ") or "[DONE]" in line:
                continue
            obj = json.loads(line[6:])
            delta = obj["choices"][0]["delta"].get("content")
            if delta:
                content += delta
            if "controlplane" in obj:
                oversight = obj["controlplane"]
    assert "4111" not in content  # the card digits were held back and never streamed
    assert oversight["action"] == "block"


def test_streaming_clean_answer_flows_through(client: TestClient) -> None:
    content = ""
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "messages": [{"role": "user", "content": "What are your customer support hours?"}],
        },
    ) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: ") and "[DONE]" not in line:
                delta = json.loads(line[6:])["choices"][0]["delta"].get("content")
                if delta:
                    content += delta
    assert "9am to 6pm" in content


def test_summary_reports_self_funding_and_valid_chain(client: TestClient) -> None:
    client.post("/v1/oversight/simulate")
    s = client.get("/v1/oversight/summary").json()
    assert s["requests"] >= 5
    assert s["net_usd"] < 0 and s["self_funding"] is True
    assert s["chain_valid"] is True
    assert s["cleared_at_t0_pct"] <= 100.0


def test_receipts_endpoints(client: TestClient) -> None:
    _chat(client, "What is the refund window?")
    recent = client.get("/v1/oversight/receipts?limit=10").json()["receipts"]
    assert recent, "expected at least one receipt"
    rid = recent[0]["request_id"]
    one = client.get(f"/v1/oversight/receipts/{rid}").json()
    assert one["request_id"] == rid
    assert one["hash_self"]  # hash-chained
    assert client.get("/v1/oversight/receipts/does-not-exist").status_code == 404


def test_policy_switch(client: TestClient) -> None:
    ok = client.post("/v1/oversight/policy", json={"policy": "internal_copilot"})
    assert ok.status_code == 200 and "internal_copilot" in ok.json()["active_policy"]
    bad = client.post("/v1/oversight/policy", json={"policy": "nope"})
    assert bad.status_code == 400


def test_replay_proof_engine(client: TestClient) -> None:
    scenarios = client.post("/v1/oversight/replay").json()["scenarios"]
    by_name = {s["name"]: s for s in scenarios}
    assert by_name["oversight_off"]["risk_reduction_pct"] == 0.0
    # Every ControlPlane policy is self-funding and reduces residual risk.
    for name in ("strict", "balanced", "lenient"):
        assert by_name[name]["net_usd"] < 0
        assert by_name[name]["risk_reduction_pct"] > 0


def test_redact_pii_labels_and_scrubs_values() -> None:
    text = "card 4111 1111 1111 1111, email jane@acme.com, call 415-555-0199"
    redacted, counts = redact_pii(text)
    assert counts["credit_card"] == 1 and counts["email"] == 1 and counts["phone"] == 1
    assert "4111" not in redacted and "jane@acme.com" not in redacted
    assert "[REDACTED_CREDIT_CARD]" in redacted


def test_models_endpoint(client: TestClient) -> None:
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert "controlplane-sim" in ids
