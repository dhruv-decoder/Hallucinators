"""Generate a tuned oversight policy (and a projection) from a plain use-case description.

Every knob is derived from a stated business fact, and the rationale explains why -- so the mapping is
legible, not a black box:

- **latency budget** -> ``lambda_latency`` (the price of a millisecond). Real-time chat pays a high price for
  latency, so the VoI rule buys fewer slow checks; a batch job pays almost nothing, so it verifies more.
- **risk tolerance** -> ``cost_fail`` on the performance axis + the action thresholds. Low tolerance raises the
  cost of a miss and lowers the thresholds, so the system verifies aggressively and escalates sooner.
- **data sensitivity** -> ``cost_fail`` on the responsibility axis + the block threshold + which model-backed
  detectors are recommended. Regulated data makes a leak very expensive and turns on the safety/PII models.
- **geography** -> which compliance frameworks apply (EU AI Act in the EU, always ISO 42001 / NIST AI RMF).

The projection extrapolates from the measured per-request economics (see the benchmark): projected added
latency, escalation rate, and monthly net savings at the stated weekly volume. It is labelled an estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controlplane.core.types import Axis, PolicyProfile

_LAMBDA = {"realtime": 5e-6, "interactive": 1e-6, "batch": 1e-7}
_PERF_COST = {"low": 2.0, "medium": 1.0, "high": 0.4}  # low tolerance for error -> high cost of a miss
_RESP_MULT = {"public": 1.0, "internal": 1.6, "regulated": 3.0}
_THRESHOLDS = {  # (block, escalate, annotate) by risk tolerance
    "low": (0.7, 0.3, 0.1),
    "medium": (0.85, 0.5, 0.2),
    "high": (0.92, 0.7, 0.4),
}
_USE_CASES = {"customer_support", "internal_copilot", "decision_support", "agentic"}


@dataclass
class UseCaseSpec:
    """A plain-language description of one enterprise AI use case."""

    use_case: str = "customer_support"
    weekly_volume: int = 50_000
    latency_budget: str = "interactive"  # realtime | interactive | batch
    risk_tolerance: str = "medium"  # low | medium | high
    data_sensitivity: str = "internal"  # public | internal | regulated
    geo: str = "EU"  # EU | US | IN | global
    name: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> UseCaseSpec:
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class GeneratedPolicy:
    """The tuned policy plus a projection and a per-knob rationale."""

    profile_id: str
    profile: PolicyProfile
    projection: dict
    rationale: list[str] = field(default_factory=list)
    recommended_detectors: list[str] = field(default_factory=list)
    compliance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        p = self.profile
        return {
            "profile_id": self.profile_id,
            "knobs": {
                "lambda_latency": p.lambda_latency,
                "cost_fail": {a.value: v for a, v in p.cost_fail.items()},
                "cost_mitigate": {a.value: v for a, v in p.cost_mitigate.items()},
                "block_threshold": p.block_threshold,
                "escalate_threshold": p.escalate_threshold,
                "annotate_threshold": p.annotate_threshold,
            },
            "projection": self.projection,
            "rationale": self.rationale,
            "recommended_detectors": self.recommended_detectors,
            "compliance": self.compliance,
        }


def generate_policy(spec: UseCaseSpec) -> GeneratedPolicy:
    """Map a use-case spec to a tuned ``PolicyProfile`` + a projection + a rationale."""
    latency = spec.latency_budget if spec.latency_budget in _LAMBDA else "interactive"
    risk = spec.risk_tolerance if spec.risk_tolerance in _PERF_COST else "medium"
    sens = spec.data_sensitivity if spec.data_sensitivity in _RESP_MULT else "internal"

    lam = _LAMBDA[latency]
    perf_cost = _PERF_COST[risk]
    resp_cost = 5.0 * _RESP_MULT[sens]
    block, escalate, annotate = _THRESHOLDS[risk]

    slug = f"{spec.use_case}@{spec.geo}@{risk}"
    profile = PolicyProfile(
        id=slug,
        cost_fail={Axis.PERFORMANCE: perf_cost, Axis.RESPONSIBILITY: resp_cost},
        cost_mitigate={Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10},
        lambda_latency=lam,
        block_threshold=block,
        escalate_threshold=escalate,
        annotate_threshold=annotate,
    )

    # --- projection (estimates from the measured per-request economics) ---
    # A higher latency price and looser thresholds mean fewer paid checks -> lower added latency + fewer
    # escalations; regulated/low-tolerance means more. These are simple monotone estimates, labelled as such.
    verify_pressure = {"low": 1.0, "medium": 0.6, "high": 0.3}[risk]
    climb_fraction = min(0.45 * verify_pressure * (1.0 if latency != "realtime" else 0.6), 0.6)
    p95_added = round(0.2 + climb_fraction * (200.0 if latency == "batch" else 60.0), 1)
    escalation_rate = round(0.02 + 0.12 * verify_pressure, 3)
    per_request_net = -0.0009 - 0.0006 * (1 if spec.use_case in ("customer_support", "agentic") else 0)
    monthly_net = round(per_request_net * spec.weekly_volume * 4.345, 2)
    human_reviews_month = int(escalation_rate * spec.weekly_volume * 4.345)

    projection = {
        "weekly_volume": spec.weekly_volume,
        "cleared_at_t0_pct": round(100.0 * (1.0 - climb_fraction), 1),
        "added_latency_p95_ms": p95_added,
        "escalation_rate": escalation_rate,
        "human_reviews_per_month": human_reviews_month,
        "projected_monthly_net_usd": monthly_net,
        "self_funding": monthly_net < 0,
        "note": "estimated from measured per-request economics at sourced prices; not a production bill",
    }

    # --- rationale (explain every knob in business terms) ---
    rationale = [
        f"Latency budget '{latency}' → price of latency λ={lam:.0e}/ms: "
        + {"realtime": "buy fewer slow checks to protect response time",
           "interactive": "balance speed and thoroughness",
           "batch": "latency is cheap, so verify aggressively"}[latency],
        f"Risk tolerance '{risk}' → cost of a missed error = {perf_cost}, thresholds "
        f"(block {block}, escalate {escalate}): "
        + {"low": "verify hard and escalate early", "medium": "balanced",
           "high": "trust more, escalate only the clearest cases"}[risk],
        f"Data sensitivity '{sens}' → cost of a responsibility failure = {resp_cost} "
        + ("(regulated data makes a leak very expensive; model-backed safety/PII enabled)"
           if sens == "regulated" else "(scaled to how sensitive the data is)"),
        f"Geography '{spec.geo}' → " + ("EU AI Act transparency & logging apply, plus ISO 42001 / NIST AI RMF"
            if spec.geo in ("EU", "global") else "ISO 42001 / NIST AI RMF"),
    ]

    recommended = ["overconfidence", "groundedness", "self_consistency", "regex_pii", "prompt_injection",
                   "unsafe_content", "bias"]
    if sens in ("internal", "regulated"):
        recommended += ["hhem_groundedness", "presidio_pii"]
    if sens == "regulated":
        recommended += ["gpt_oss_safeguard", "llm_judge"]
    if spec.use_case == "agentic":
        recommended += ["trajectory_audit"]

    compliance = ["ISO/IEC 42001", "NIST AI RMF"]
    if spec.geo in ("EU", "global"):
        compliance.insert(0, "EU AI Act (Art. 12 logging, 13 transparency, 14 human oversight, 50 disclosure)")

    return GeneratedPolicy(
        profile_id=slug, profile=profile, projection=projection, rationale=rationale,
        recommended_detectors=recommended, compliance=compliance,
    )
