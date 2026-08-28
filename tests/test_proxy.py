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


def test_demo_traffic_uses_real_cache_bypass(client: TestClient) -> None:
    # The demo workload repeats one prompt, so a real cache bypass must keep upstream_calls below the
    # request count. Re-firing it should NOT increase upstream_calls at all (every prompt is now cached).
    first = client.post("/v1/oversight/simulate").json()
    assert first["cache_hits"] >= 1
    assert first["upstream_calls"] < first["processed"]  # the repeat was served from cache, not the upstream
    calls_after_first = first["upstream_calls"]
    second = client.post("/v1/oversight/simulate").json()
    assert second["upstream_calls"] == calls_after_first  # flat: nothing new hit the upstream
    assert second["cache_hits"] > first["cache_hits"]  # but the bypass counter keeps climbing


def test_voi_contrast_endpoint_shows_skip_and_buy(client: TestClient) -> None:
    v = client.get("/v1/oversight/voi-contrast").json()
    assert v["safe"]["bought_a_check"] is False
    assert v["uncertain"]["bought_a_check"] is True
    assert v["safe"]["action"] == "pass"


def test_api_key_auth_gate(monkeypatch) -> None:
    # Off by default: with no key configured, /v1 is open (the fixture client already proves this).
    open_client = TestClient(create_app(recorder_path=None, force_simulated=True))
    assert open_client.get("/v1/oversight/summary").status_code == 200

    # With CONTROLPLANE_API_KEY set (read at app-build time), /v1 requires it; /readyz stays open.
    monkeypatch.setenv("CONTROLPLANE_API_KEY", "secret123")
    c = TestClient(create_app(recorder_path=None, force_simulated=True))
    assert c.get("/v1/oversight/summary").status_code == 401
    assert c.get("/v1/oversight/summary", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/v1/oversight/summary", headers={"Authorization": "Bearer secret123"}).status_code == 200
    assert c.get("/readyz").status_code == 200  # health probe is never gated


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


def test_dashboard_and_static_assets_served(client: TestClient) -> None:
    assert "<title>ControlPlane" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_healthz_reports_models(client: TestClient) -> None:
    h = client.get("/healthz").json()
    assert h["ok"] is True
    assert set(h["models"]) == {"groundedness", "pii", "safety", "judge"}


def test_playground_oversees_a_prompt(client: TestClient) -> None:
    # No provider key in tests -> falls back to the offline upstream; still overseen end to end.
    r = client.post("/v1/oversight/playground",
                    json={"prompt": "Can you share the customer's payment details?", "model": "gpt-4o-mini"}).json()
    assert r["source"] == "simulated"
    assert "candidate" in r and "final" in r
    assert r["controlplane"]["action"] == "block"
    assert r["receipt"]["hash_self"]
    assert client.post("/v1/oversight/playground", json={"prompt": ""}).status_code == 400


def test_route_down_actually_serves_the_cheaper_model(client: TestClient) -> None:
    # A simple prompt on a flagship is genuinely served by the cheaper model (P0.2), not just booked.
    simple = {"prompt": "Where can I download the app?", "model": "gpt-4o"}
    r = client.post("/v1/oversight/playground", json=simple).json()
    assert r["routed_down"] is True
    assert r["requested_model"] == "gpt-4o" and r["served_by"] == "gpt-4o-mini"
    assert r["economics"]["route_down_avoided_flagship_usd"] > 0
    # A complex prompt keeps the flagship (quality guard).
    hard = {"prompt": "Write code to refactor this SQL and prove it step by step", "model": "gpt-4o"}
    r2 = client.post("/v1/oversight/playground", json=hard).json()
    assert r2["routed_down"] is False and r2["served_by"] == "gpt-4o"


def test_cache_actually_bypasses_the_upstream_on_repeat(client: TestClient) -> None:
    # Two identical requests: the second must be served from cache without a new upstream call (P0.3).
    p = {"prompt": "What are the customer support hours?", "context": "Open 9-6.", "model": "gpt-4o"}
    r1 = client.post("/v1/oversight/playground", json=p).json()
    r2 = client.post("/v1/oversight/playground", json=p).json()
    assert r1["cache_hit"] is False and r2["cache_hit"] is True
    # The upstream-call counter did not advance on the cache hit -> the model was genuinely not called.
    assert r2["economics"]["upstream_calls"] == r1["economics"]["upstream_calls"]
    assert r2["economics"]["cache_hits"] >= 1
    assert r2["economics"]["model_cost_avoided_usd"] > 0



def test_semantic_cache_paraphrase_is_a_real_bypass(client: TestClient, monkeypatch) -> None:
    import numpy as np

    service = client.app.state.service
    service.semantic_cache.enabled = True
    service.semantic_cache.mode = "semantic"
    service.semantic_cache._embedder = lambda _: np.array([1.0, 0.0])

    first = client.post(
        "/v1/oversight/playground", json={"prompt": "What are customer support hours?", "model": "gpt-4o"}
    )
    assert first.status_code == 200
    calls_after_first = first.json()["economics"]["upstream_calls"]

    second = client.post(
        "/v1/oversight/playground",
        json={"prompt": "Can you tell me the customer support hours?", "model": "gpt-4o"},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["cache_hit"] is True
    assert body["economics"]["upstream_calls"] == calls_after_first
    assert body["receipt"]["cost_opportunities"][1]["recommendation"] == "cache_hit"
    assert body["receipt"]["cost_opportunities"][1]["detail"]["kind"] == "semantic"


def test_conformal_endpoint_returns_certificates(client: TestClient) -> None:
    data = client.get("/v1/oversight/conformal").json()
    assert data["axis"] == "performance"
    alphas = {c["alpha"] for c in data["certificates"]}
    assert alphas == {0.30, 0.20, 0.10}
    for c in data["certificates"]:
        assert "statement" in c and "valid" in c


def test_benchmark_job_runs_with_progress(client: TestClient) -> None:
    import time

    started = client.post("/v1/oversight/jobs/benchmark?n=300&weekly_volume=50000").json()
    job_id = started["id"]
    for _ in range(100):
        snap = client.get(f"/v1/oversight/jobs/{job_id}").json()
        if snap["status"] != "running":
            break
        time.sleep(0.05)
    assert snap["status"] == "done"
    r = snap["result"]
    assert set(r["added_latency_ms"]) == {"p50", "p95", "p99", "mean"}
    assert r["throughput_rps"] > 0
    assert r["at_scale"]["weekly_volume"] == 50000
    assert client.get("/v1/oversight/jobs/nope").status_code == 404
