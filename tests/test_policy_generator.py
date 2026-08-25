"""Tests for the use-case policy generator and its endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from controlplane.core.types import Axis
from controlplane.policy import UseCaseSpec, generate_policy
from controlplane.proxy.app import create_app


def test_latency_budget_maps_to_lambda() -> None:
    realtime = generate_policy(UseCaseSpec(latency_budget="realtime")).profile.lambda_latency
    batch = generate_policy(UseCaseSpec(latency_budget="batch")).profile.lambda_latency
    assert realtime > batch  # real-time prices latency higher -> buys fewer slow checks


def test_low_risk_verifies_harder_than_high_risk() -> None:
    low = generate_policy(UseCaseSpec(risk_tolerance="low")).profile
    high = generate_policy(UseCaseSpec(risk_tolerance="high")).profile
    assert low.cost_fail[Axis.PERFORMANCE] > high.cost_fail[Axis.PERFORMANCE]
    assert low.escalate_threshold < high.escalate_threshold  # low tolerance escalates sooner


def test_regulated_data_raises_responsibility_cost_and_recommends_models() -> None:
    reg = generate_policy(UseCaseSpec(data_sensitivity="regulated"))
    pub = generate_policy(UseCaseSpec(data_sensitivity="public"))
    assert reg.profile.cost_fail[Axis.RESPONSIBILITY] > pub.profile.cost_fail[Axis.RESPONSIBILITY]
    assert "gpt_oss_safeguard" in reg.recommended_detectors
    assert any("EU AI Act" in c for c in generate_policy(UseCaseSpec(geo="EU")).compliance)


def test_projection_and_rationale_present() -> None:
    g = generate_policy(UseCaseSpec(weekly_volume=100_000)).to_dict()
    assert g["projection"]["weekly_volume"] == 100_000
    assert "projected_monthly_net_usd" in g["projection"]
    assert len(g["rationale"]) >= 4


def test_generate_endpoint_and_apply() -> None:
    client = TestClient(create_app(recorder_path=None, force_simulated=True))
    r = client.post("/v1/oversight/policy/generate?apply=1",
                    json={"use_case": "decision_support", "risk_tolerance": "low",
                          "data_sensitivity": "regulated", "geo": "EU", "weekly_volume": 80000}).json()
    assert r["applied"] is True
    assert r["knobs"]["cost_fail"]["responsibility"] > 5.0
    # The generated profile is now the active policy.
    assert client.get("/v1/oversight/summary").json()["active_policy"] == r["profile_id"]
