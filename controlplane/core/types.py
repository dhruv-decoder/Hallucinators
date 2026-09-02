"""Frozen contracts shared across every ControlPlane layer.

These are the objects that flow through the system. Freezing their shapes early is what lets the
engine (P1), the proxy/recorder (P2), and the UI (P3) be built in parallel without colliding.

Data flow, end to end::

    RequestContext            # the prompt + candidate response + any retrieved context
        -> Detector.run()     # each detector emits a Signal (a risk score on one axis)
        -> CascadeEngine      # combines signals into a per-axis P(failure); applies the VoI stopping rule
        -> CascadeResult      # the decision, the per-axis outcome, and the full VoI trace
        -> ReceiptBuilder     # turns the result + P&L into a hash-chained VoIReceipt
        -> Recorder           # appends the receipt to the tamper-evident flight log

All monetary values are in USD. All latencies are in milliseconds. Probabilities are in [0, 1].
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field


class Axis(str, enum.Enum):
    """The three coupled risks ControlPlane watches on every response."""

    PERFORMANCE = "performance"  # wrong, or confidently wrong
    COST = "cost"  # wasteful compute / a cheaper path to the same quality exists
    RESPONSIBILITY = "responsibility"  # biased, unsafe, or leaking data


class Tier(enum.IntEnum):
    """Cost/latency tiers a detector can belong to. Higher tier = more accurate but more expensive.

    The whole point of the cascade is to resolve most responses at T0 and only climb when the
    value of the next tier's information beats its cost.
    """

    T0 = 0  # free-ish heuristics, ~1-5 ms
    T1 = 1  # cheap models, ~20-60 ms
    T2 = 2  # costly models / LLM-judge / human, ~200 ms and up


class Action(str, enum.Enum):
    """The action ControlPlane takes on a response after the cascade runs.

    This is the brief's second explicit question: allow / edit / flag / block, plus who is pulled in.
    """

    PASS = "pass"  # confident and clean -> forward unchanged
    ANNOTATE = "annotate"  # honest uncertainty -> forward with a caveat
    AUTO_REPAIR = "auto_repair"  # fixable inline -> forward a corrected version
    ESCALATE = "escalate"  # high-stakes and uncertain -> route to a human
    BLOCK = "block"  # clear policy violation -> do not forward


class Signal(BaseModel):
    """One detector's read on one axis for one response.

    ``score`` is the detector's raw risk in [0, 1] (higher = more likely a failure). ``p_fail`` is the
    calibrated probability the engine fills in after passing ``score`` through the axis calibrator; before
    calibration it defaults to the raw score. ``cost_usd`` and ``latency_ms`` are what running this
    detector actually cost, which feed both the stopping rule and the P&L.
    """

    name: str
    axis: Axis
    tier: Tier
    score: float = Field(ge=0.0, le=1.0)
    p_fail: float | None = Field(default=None, ge=0.0, le=1.0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    detail: dict = Field(default_factory=dict)


class CostAction(str, enum.Enum):
    """What a cost-axis detector recommends. The cost axis is the *funding* side of oversight:
    instead of estimating a failure probability, it finds cheaper paths to the same quality."""

    NONE = "none"
    ROUTE_DOWN = "route_down"  # a smaller model would answer this as well
    CACHE_HIT = "cache_hit"  # a near-identical request was already answered
    COMPRESS = "compress"  # the prompt/response can be shortened without losing quality


class CostOpportunity(BaseModel):
    """A cost-axis finding: a way to have produced this quality more cheaply.

    ``estimated_savings_usd`` is the counterfactual spend avoided (e.g. flagship price minus the cheaper
    path). It is what the P&L ledger books on the "cost saved" side.
    """

    name: str
    tier: Tier
    recommendation: CostAction
    estimated_savings_usd: float = Field(default=0.0, ge=0.0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    detail: dict = Field(default_factory=dict)


class RequestContext(BaseModel):
    """Everything a detector may look at for a single request/response pair.

    ``response`` is the candidate model output under review. ``retrieved_context`` is the source text a
    RAG system grounded on (used by groundedness detectors). ``samples`` are extra independent
    generations for the same prompt, used by self-consistency / semantic-entropy detectors.
    """

    request_id: str
    use_case: str = "default"
    prompt: str = ""
    response: str = ""
    retrieved_context: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    meta: dict = Field(default_factory=dict)


class PolicyProfile(BaseModel):
    """The knobs that make oversight vary by use case, geography, and risk appetite.

    This is the minimal frozen schema (P1). P2 owns the loader, validation, hot-reload, and the full set
    of per-geography/per-risk profiles built on top of it.

    The economic parameters drive the VoI stopping rule (see ``controlplane/cascade/voi.py``):

    - ``cost_fail``: the business cost if a failure on this axis reaches the user. Raising it makes the
      system verify more aggressively on that axis (fewer false negatives).
    - ``cost_mitigate``: the cost of the mitigating action (escalate/block/repair) -- friction, human
      time, latency. Raising it makes the system less trigger-happy (fewer false positives).
    - ``lambda_latency``: the price (USD per millisecond) we put on added latency. This is how a
      latency budget enters the decision: a real-time chatbot uses a higher value than a batch job.
    - ``block_threshold`` / ``escalate_threshold``: calibrated-probability cutoffs the reference
      decision function uses to choose an action.
    """

    id: str = "default@balanced"
    cost_fail: dict[Axis, float] = Field(
        default_factory=lambda: {Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0}
    )
    cost_mitigate: dict[Axis, float] = Field(
        default_factory=lambda: {Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10}
    )
    lambda_latency: float = 1e-6  # USD per ms of added oversight latency
    block_threshold: float = 0.85
    escalate_threshold: float = 0.5
    annotate_threshold: float = 0.2


class AxisOutcome(BaseModel):
    """The engine's final read on one failure-type axis (performance / responsibility)."""

    axis: Axis
    p_fail: float = Field(ge=0.0, le=1.0)
    expected_loss: float = Field(ge=0.0)
    signals: list[Signal] = Field(default_factory=list)


class VoIStep(BaseModel):
    """One decision point in the cascade, recorded for explainability.

    Every time the engine considers running a detector, it records what it estimated the check was
    worth (``voi``), what the check would cost (``check_cost``), and whether it ran it. This trace is
    what makes a receipt auditable -- you can see exactly why the engine stopped where it did.
    """

    axis: Axis
    detector: str
    tier: Tier
    p_fail_before: float
    p_fail_after: float | None = None
    voi: float
    check_cost: float
    ran: bool
    reason: str


class PnlEntry(BaseModel):
    """The Oversight P&L for a single request. ``net_usd`` negative means oversight paid for itself.

    ``model_cost_usd`` is the base cost of the model call itself (tokens x price). On the live Playground path
    the token counts come from the provider's ``usage`` (measured); ``cost_saved_usd`` and ``safety_spend_usd``
    are still estimated (list price, nominal check cost) -- see the P&L ledger for the exact provenance.
    """

    model_cost_usd: float = 0.0
    cost_saved_usd: float = 0.0
    safety_spend_usd: float = 0.0
    token_source: str = "estimated"  # "measured" when tokens come from a real provider's usage metadata

    # A plain @property is invisible to ``model_dump()``, so ``net_usd`` never reached the JSON the UI
    # reads -- every per-decision net figure rendered as NaN and the cumulative benefit chart stayed empty.
    # ``computed_field`` keeps it derived (there is still exactly one definition of the arithmetic) while
    # making it part of the serialised receipt, which is also what the hash chain should be committing to.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_usd(self) -> float:
        """Safety spend minus cost saved. Negative = self-funding (we saved more than we spent)."""
        return self.safety_spend_usd - self.cost_saved_usd


class Transcript(BaseModel):
    """The text behind one decision, as it is safe to store in the audit log.

    A receipt that records *only* scores and thresholds is unreadable: an auditor (or a reviewer working the
    escalation queue) cannot judge whether "p_fail 0.91 -> block" was right without seeing what was asked and
    what the model actually said. So every receipt carries the transcript -- but PII is redacted first, with
    the same detector that decides the response is a leak, so the audit log never becomes a second copy of
    the data we just blocked. ``redacted`` records what was removed (entity type -> count) as evidence.
    """

    prompt: str = ""
    response: str = ""  # the model's candidate output, redacted
    delivered: str = ""  # what the user actually received after the action was applied, redacted
    retrieved_context: list[str] = Field(default_factory=list)
    model: str = ""
    redacted: dict[str, int] = Field(default_factory=dict)
    truncated: bool = False


class CascadeResult(BaseModel):
    """The engine's full output for one request, before it becomes a receipt."""

    request_id: str
    use_case: str
    prompt: str = ""
    response: str = ""
    retrieved_context: list[str] = Field(default_factory=list)
    model: str = ""
    per_axis: dict[Axis, AxisOutcome] = Field(default_factory=dict)
    signals: list[Signal] = Field(default_factory=list)
    cost_opportunities: list[CostOpportunity] = Field(default_factory=list)
    expected_loss_before: float = 0.0
    expected_loss_after: float = 0.0
    action: Action = Action.PASS
    stopping_reason: str = ""
    trace: list[VoIStep] = Field(default_factory=list)


class VoIReceipt(BaseModel):
    """The immutable, human-readable record of one oversight decision.

    This is both the audit trail the brief asks for and the object the UI renders. It is hash-chained by
    the recorder: ``hash_self = sha256(canonical(receipt without hash_self) + hash_prev)``.
    """

    request_id: str
    use_case: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transcript: Transcript = Field(default_factory=Transcript)
    signals: list[Signal] = Field(default_factory=list)
    cost_opportunities: list[CostOpportunity] = Field(default_factory=list)
    per_axis: dict[Axis, AxisOutcome] = Field(default_factory=dict)
    expected_loss_before: float = 0.0
    expected_loss_after: float = 0.0
    stopping_reason: str = ""
    action: Action = Action.PASS
    repaired_output: str | None = None
    pnl: PnlEntry = Field(default_factory=PnlEntry)
    trace: list[VoIStep] = Field(default_factory=list)
    policy_id: str = "default@balanced"
    hash_prev: str = ""
    hash_self: str = ""
