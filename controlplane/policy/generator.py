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
# How hard each risk appetite pushes the cascade to climb past the free tier. Named so the projection can
# publish the constant it used rather than hiding a magic number inside the arithmetic.
_VERIFY_PRESSURE = {"low": 1.0, "medium": 0.6, "high": 0.3}


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
    verify_pressure = _VERIFY_PRESSURE[risk]
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

    # --- how each projected number was derived ---------------------------------------------------
    # Every figure above is a closed-form function of the spec, not a simulation and not a measurement.
    # We publish the inputs, the formula, and the arithmetic for each one so a reader can check it by hand
    # (and so nobody mistakes a projection for a bill). See `estimate_method` below for the caveats.
    extra_net_note = (
        "; -$0.0006 extra for a high-cache-hit use case"
        if spec.use_case in ("customer_support", "agentic")
        else ""
    )
    tier_latency_note = (
        "batch tolerates the T2 model tier"
        if latency == "batch"
        else "interactive/real-time stays on the T1 tier"
    )
    steps = [
        {
            "metric": "Cleared at T0",
            "value": f"{round(100.0 * (1.0 - climb_fraction), 1)}%",
            "formula": "100 x (1 - climb_fraction)",
            # LaTeX so the UI can typeset the rule and the substitution rather than printing ASCII.
            "latex": r"\text{cleared}_{T0} = 100 \times (1 - f_{\text{climb}})",
            "latex_substituted": (
                rf"f_{{\text{{climb}}}} = \min(0.45 \times {verify_pressure} \times "
                rf"{1.0 if latency != 'realtime' else 0.6},\; 0.60) = {round(climb_fraction, 4)}"
            ),
            "inputs": [
                f"verify_pressure = {verify_pressure} (from risk tolerance '{risk}')",
                f"realtime_discount = {1.0 if latency != 'realtime' else 0.6} (latency budget '{latency}')",
            ],
            "meaning": "share of responses the free T0 tier settles, so no paid check is ever bought for them",
        },
        {
            "metric": "Added latency p95",
            "value": f"{p95_added} ms",
            "formula": "0.2 ms + climb_fraction x tier_latency",
            "latex": r"\ell_{p95} = 0.2 + f_{\text{climb}} \times \ell_{\text{tier}}",
            "latex_substituted": (
                rf"\ell_{{p95}} = 0.2 + {round(climb_fraction, 4)} \times "
                rf"{200.0 if latency == 'batch' else 60.0} = {p95_added}\ \text{{ms}}"
            ),
            "inputs": [
                f"tier_latency = {200.0 if latency == 'batch' else 60.0} ms ({tier_latency_note})",
            ],
            "meaning": "the oversight layer's own p95 overhead; the model call itself is unchanged",
        },
        {
            "metric": "Escalation rate",
            "value": f"{round(escalation_rate * 100, 1)}%",
            "formula": "2% base + 12% x verify_pressure",
            "latex": r"r_{\text{esc}} = 0.02 + 0.12 \times p_{\text{verify}}",
            "latex_substituted": rf"r_{{\text{{esc}}}} = 0.02 + 0.12 \times {verify_pressure} = {escalation_rate}",
            "inputs": [f"verify_pressure = {verify_pressure} (risk tolerance '{risk}')"],
            "meaning": "share routed to a person; lower risk tolerance deliberately escalates more",
        },
        {
            "metric": "Human reviews per month",
            "value": f"{human_reviews_month:,}",
            "formula": "escalation_rate x weekly_volume x 4.345 weeks",
            "latex": r"N_{\text{review}} = r_{\text{esc}} \times V_{\text{week}} \times 4.345",
            "latex_substituted": (
                rf"N_{{\text{{review}}}} = {escalation_rate} \times {spec.weekly_volume:,} "
                rf"\times 4.345 = {human_reviews_month:,}".replace(",", "{,}")
            ),
            "inputs": [f"weekly_volume = {spec.weekly_volume:,} (the figure you entered)"],
            "meaning": "the analyst workload this policy creates, a real cost booked separately",
        },
        {
            "metric": "Projected net benefit per month",
            "value": f"${abs(monthly_net):,.2f}" + (" saved" if monthly_net < 0 else " cost"),
            "formula": "per_request_net x weekly_volume x 4.345 weeks",
            "latex": r"B_{\text{month}} = b_{\text{req}} \times V_{\text{week}} \times 4.345",
            "latex_substituted": (
                rf"B_{{\text{{month}}}} = {per_request_net:.4f} \times {spec.weekly_volume:,} "
                rf"\times 4.345 = {monthly_net}".replace(",", "{,}")
            ),
            "inputs": [
                f"per_request_net = ${per_request_net:.4f} (base -$0.0009{extra_net_note})",
            ],
            "meaning": "cost-axis savings minus safety-check spend; negative means self-funding",
        },
    ]

    estimate_method = {
        "basis": (
            "A closed-form model, not a simulation. Each figure is a monotone function of the five spec "
            "inputs, anchored on the per-request economics measured on the live-model path (see Oversight "
            "P&L) and on published provider list prices."
        ),
        "constants": {
            "verify_pressure": _VERIFY_PRESSURE,
            "lambda_latency_usd_per_ms": _LAMBDA,
            "cost_of_a_miss": _PERF_COST,
            "responsibility_multiplier": _RESP_MULT,
            "weeks_per_month": 4.345,
            "base_per_request_net_usd": -0.0009,
        },
        "steps": steps,
        "caveats": [
            "Volume is the figure you entered, not observed traffic.",
            "Per-request net is anchored on this deployment's measured runs; your traffic mix will differ.",
            "Human review cost is excluded from the net. It is shown as its own line so the automated "
            "and the human economics never get blended.",
            "Latency is the oversight layer's overhead only; it excludes the model call.",
        ],
    }
    projection["estimate_method"] = estimate_method

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
