# Architecture Decision Records

Short records of the decisions behind the engine, in context → decision → consequences form. These are
the "why" questions the AI discussion will probe.

## ADR-0001 — Oversight is a value-of-information decision under a latency budget
**Context.** Existing tools bolt a fixed verification step onto every response (a safety tax) or only
observe after the fact. **Decision.** Model each check as an economic choice: run it only when its expected
reduction in loss beats its dollar + latency cost. **Consequences.** One decision rule spans all three
axes; the same knobs tune over/under-flagging and latency; the mechanism is novel and defensible. Requires
calibrated probabilities and per-axis cost parameters.

## ADR-0002 — Additive per-axis expected-loss decomposition
**Context.** We need an overall loss from several axes. **Decision.** Sum per-axis expected losses
(`sum p_axis * Cost_axis`), each axis with its own failure cost. **Consequences.** Simple and interpretable;
each axis is tuned independently. It ignores cross-axis correlation (a fabricated fact about a person is
both a hallucination and a privacy leak); acceptable for now, revisit if correlations matter.

## ADR-0003 — Calibrate detector scores; implement Platt and isotonic from scratch
**Context.** Raw detector scores are not probabilities, but the VoI math needs probabilities.
**Decision.** Learn a score→failure-rate map (Platt or isotonic via PAV), implemented without sklearn.
**Consequences.** Honest expected-loss arithmetic and a reliability diagram for skeptics; every step is
explainable in the AI discussion. Slightly more code than importing a library, which is the point.

## ADR-0004 — The cost axis is the funding side, handled separately from failure-loss VoI
**Context.** "Cost" is not a harmful failure with a probability; it is waste with a savings opportunity.
**Decision.** Cost detectors emit savings opportunities, not failure probabilities; the ledger books them
against safety spend. **Consequences.** The self-funding story is explicit and measurable; the VoI failure
machinery stays clean. Cost checks are effectively always-on because they are free.

## ADR-0005 — T0 always-on and free; T1/T2 gated by the stopping rule; the lexical groundedness check is T0
**Context.** We need cheap signals to trigger expensive ones, and calm hallucinations must not be missed.
**Decision.** Free heuristics (including lexical groundedness) run on every request; only paid checks
(sampling, model-backed judges) are VoI-gated. **Consequences.** Cheap suspicion drives expensive
verification; groundedness catches even unhedged fabrications when context exists. The model-based
groundedness detector remains a T1 upgrade.

## ADR-0006 — Combine per-axis signals with noisy-OR
**Context.** Several detectors may fire on one axis. **Decision.** Combine calibrated probabilities via
noisy-OR by default (`max`, `mean` available). **Consequences.** Interpretable ("at least one detector is
right") and monotone. Can over-inflate with many weak, correlated detectors; mitigated by re-calibrating
the combined score.

## ADR-0007 — Hash-chained JSONL flight recorder now; SQLite later
**Context.** Every decision needs an auditable, tamper-evident record. **Decision.** A reference append-only
JSONL store with a SHA-256 hash chain. **Consequences.** Runs with no dependencies and detects tampering;
we describe it as tamper-evident, not immutable. P2 replaces it with a SQLite recorder plus a query API for
the UI, keeping the same `append` / `verify_chain` interface.

## ADR-0008 — A reference decision function stands in for the policy engine
**Context.** Action selection (pass/annotate/escalate/block) is governance that varies by use case,
geography, and risk. **Decision.** Ship a simple threshold reference now; P2 builds the config-driven policy
engine. **Consequences.** The pipeline runs end to end today; the interface (per-axis outcomes + policy →
action) is stable for P2 to build behind.

## ADR-0009 — AUTO_REPAIR is defined but not emitted yet
**Context.** Faithful repair needs a corrective generation, which arrives with the model/proxy layer.
**Decision.** Keep `AUTO_REPAIR` in the action enum but do not emit it until the corrective hook exists.
**Consequences.** No fabricated capability; the demo shows only actions we can actually perform.

## ADR-0010 — Illustrative pricing placeholders, pending sourced values
**Context.** The P&L needs prices to produce numbers, but we must not publish unverified figures.
**Decision.** Ship clearly-labelled placeholder prices; require real, sourced prices in `docs/EVIDENCE.md`
before any figure appears in a slide, README, or video. **Consequences.** The demo runs; credibility is
protected by the evidence gate.

## ADR-0011 — Synchronous engine now; parallel detectors later
**Context.** Latency matters, but decision correctness comes first. **Decision.** Implement the tier loop
synchronously; leave within-tier parallelism (asyncio) to the proxy layer. **Consequences.** The core is
easy to read, test, and explain; the parallel-for-latency optimisation is additive and does not change the
stopping-rule logic.

## ADR-0012 — What-If/Replay measures residual risk, holding the risk model constant
**Context.** We need to *prove* "safer AND cheaper" on identical traffic, not assert it, without real
ground-truth labels (those come later from the eval harness). **Decision.** Re-run a fixed workload under
each policy and report residual risk (estimated expected loss of answers that still reach users, i.e. the
pass/annotate ones) and net cost; model "oversight off" as forwarding everything with no savings; and vary
only the risk *appetite* (action thresholds) while holding the risk model (`cost_fail`) constant so
`total_risk` is identical across scenarios. **Consequences.** A clean, monotonic dial (stricter = safer but
more escalations) and a defensible self-funding number, clearly labelled as ControlPlane's own estimates
rather than measured failure rates. The labelled eval harness will later replace estimates with measured
precision/recall.

## Known open issue — base-rate blind spot
If all cheap T0 detectors are silent, an axis starts near p=0 and the VoI rule may skip paid checks, so a
calm, contextless hallucination could slip through. Planned fix: a per-axis prior base rate plus cheap
always-on detectors that need no context. Tracked here until addressed.
