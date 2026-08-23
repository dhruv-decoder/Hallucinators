# Architecture

How the ControlPlane oversight engine works, end to end. This describes what is implemented today — the
decision engine, the What-If/Replay simulator, **and now the OpenAI-compatible proxy (The Tower) and the
Control-Tower dashboard** (section 14). The richer model-backed detectors are tracked in [PLAN.md](PLAN.md).
For a gentler, diagram-led tour of the whole system and the user flow, read [WALKTHROUGH.md](WALKTHROUGH.md).

## 1. The one idea

Oversight is a **value-of-information (VoI) decision under a latency budget**. For every response and
every axis we ask: *is running the next, more expensive check worth it?* We only pay for a check when the
expected reduction in loss it buys exceeds what the check itself costs in dollars and latency. Most
responses are resolved by free T0 heuristics; we climb tiers only when the numbers say to.

## 2. Data flow

```
RequestContext                     prompt + candidate response + retrieved context + samples
   -> Detector.run()               each detector emits a Signal (risk score on one axis) or a CostOpportunity
   -> CascadeEngine.run()          calibrate -> combine -> VoI stopping rule per axis -> action
   -> CascadeResult                per-axis p_fail, expected loss before/after, full VoI trace
   -> PnlLedger.book()             cost saved (cost axis) vs safety spend (checks) = net
   -> build_receipt()              hash-chained VoIReceipt
   -> JsonlRecorder                append-only, tamper-evident flight log
```

The contracts for every object are in [`controlplane/core/types.py`](../controlplane/core/types.py) and are
frozen so the engine (P1), proxy/recorder (P2), and UI (P3) can be built against stable shapes.

## 3. The three axes

- **Performance** (failure-type): wrong, or confidently wrong. Detectors: overconfidence (T0), lexical
  groundedness vs retrieved context (T0), self-consistency across samples (T1). Upgrades: HHEM/MiniCheck,
  semantic entropy.
- **Responsibility** (failure-type): biased, unsafe, leaking. Detectors: regex/Luhn PII (T0), plus an
  optional Presidio + spaCy **NER PII detector** (T0, `[ml]` extra) that catches free-text identifiers
  (names, locations) the regex is blind to. Upgrades: safety classifiers, Llama-Guard-class review.
- **Cost** (funding side): a cheaper path to the same quality. Detectors: model-overkill (T0), semantic
  cache (T0). Upgrades: a learned router, embedding near-duplicate cache. Its savings **fund** the other
  two axes, which is why oversight can net negative.

Failure-type axes go through the VoI machinery below. The cost axis does not estimate a failure
probability; it books savings into the P&L.

## 4. The VoI stopping rule (the core math)

For a failure-type axis, with `p` = calibrated failure probability, `C` = cost if the failure reaches the
user, `m` = cost of the mitigating action (escalate/block/repair):

- **Best action now, no more info:** either pass (risk `p*C`) or mitigate (`m`); take the cheaper.
  `bayes_risk = min(p*C, m)`.
- **After a perfect check:** loss is `p*min(m, C)` (mitigate true failures, pass the rest).
- **Value of a real check** resolving a fraction `eta` (informativeness) of the uncertainty:
  `VoI = eta * ( min(p*C, m) - p*min(m, C) )`, always non-negative.
- **Stopping rule:** run the next check iff `VoI > check_cost`, where
  `check_cost = cost_usd + lambda_latency * latency_ms`.

`C`, `m`, and `lambda_latency` come from the active `PolicyProfile`, so one set of per-use-case knobs tunes
the whole over-flag / under-flag / latency trade-off. The two regimes fall out automatically: when we would
otherwise pass, the check earns its keep by catching real failures cheaply; when we would otherwise
mitigate, it earns its keep by clearing false alarms. Implementation:
[`controlplane/cascade/voi.py`](../controlplane/cascade/voi.py).

## 5. Calibration

The stopping rule needs `p` to be a real probability, so raw detector scores are mapped to failure rates
learned on held-out labelled data. Two methods are implemented from scratch (no sklearn) so we can explain
them: **Platt** (sigmoid via logistic regression) and **isotonic** (monotone step-fit via
Pool-Adjacent-Violators). `expected_calibration_error` reports the gap. Before any labelled data exists we
use an honest `IdentityCalibrator` (raw score = probability) and say it is uncalibrated. Implementation:
[`controlplane/cascade/calibration.py`](../controlplane/cascade/calibration.py).

## 6. Combining signals

Multiple detectors on one axis are combined into a single `p` via **noisy-OR**
(`1 - prod(1 - p_i)`) by default: the probability that at least one detector is right that this is a
failure. `max` and `mean` are also available. The combined score can itself be re-calibrated.

## 7. Action, P&L, and the receipt

A reference decision function ([`decision.py`](../controlplane/cascade/decision.py)) maps final per-axis
probabilities to pass / annotate / escalate / block using policy thresholds; P2's policy engine will
replace it with the full config-driven version. The `PnlLedger` books cost saved against safety spend. The
recorder builds a `VoIReceipt` — the human-readable audit record — and chains it by SHA-256 so the log is
**tamper-evident** (each receipt's hash covers its contents and the previous hash; altering any past
receipt breaks every later link). This is not "immutable"; we say what it actually is.

## 8. Concurrency

The tier loop is sequential by design — whether to climb depends on what cheaper tiers found. Detectors
*within* a tier are independent and can run in parallel; that async concurrency is a latency optimisation
owned by the proxy layer (P2) and does not change the decision logic.

## 9. Replay / What-If (the proof engine)

To show "safer AND cheaper" rather than assert it, the What-If simulator
([`controlplane/replay/simulator.py`](../controlplane/replay/simulator.py)) re-runs a fixed workload under
several policies and against an "oversight off" baseline. For each it reports **residual risk** (the
model-estimated expected loss of answers that still reach users) and **net cost** (savings minus safety
spend). Risk appetite (the action thresholds) varies while the risk model (`cost_fail`) is held constant,
so total estimated risk is identical across scenarios and only what we *do* about it changes. The result is
a monotonic dial: stricter policies cut residual risk further but escalate more to humans, and every
ControlPlane policy is self-funding. These are ControlPlane's own risk estimates, not ground-truth failure
rates; the labelled eval harness will measure the latter. Run it with `make whatif`.

## 10. Adaptive Oversight Thermostat

Thoroughness should not be fixed: a quiet hour and a risk spike deserve different scrutiny. The thermostat
([`controlplane/cascade/thermostat.py`](../controlplane/cascade/thermostat.py)) is a proportional
controller over a sliding window of recent risk (the max calibrated failure probability per request). It
outputs a *scrutiny* multiplier, `scrutiny = clip(1 + gain * (recent_mean_risk - setpoint), s_min, s_max)`,
which the stopping rule applies to the value of information (`voi.decide_check`). Above 1.0 the system runs
more paid checks; below 1.0 it relaxes. It is causal — scrutiny for a request is set from risk seen on
previous requests — so a burst of risky traffic ramps scrutiny up over the next few requests and it decays
once calm returns. At the default `scrutiny=1.0` the engine behaves exactly as the plain VoI rule, so the
controller is strictly additive. Run it with `make thermostat`.

## 11. Feedback loop (learning from overrides)

Detection should improve as humans review flagged cases. When a reviewer overrides an escalation or block
and states whether the response really was a failure on an axis, that verdict is ground truth for every
detector that fired on that axis. The feedback loop
([`controlplane/feedback/loop.py`](../controlplane/feedback/loop.py)) accumulates those
`(detector_score, true_label)` pairs and refits each detector's calibrator (reusing
`cascade/calibration.py`), which the engine then uses in place of the identity default. In the demo, 300
reviews cut the overconfidence detector's calibration error from ~0.40 to ~0.01, and a confident-but-correct
answer that was being escalated is downgraded — the over-flagging is corrected without touching any
detector's code. Detectors with too little feedback keep their default calibration, so we never fit a curve
from a handful of points. Run it with `python -m controlplane.demo.run_feedback`.

## 12. Evaluation harness (measured quality)

Detection quality is measured, not asserted. The harness
([`controlplane/eval/`](../controlplane/eval/)) runs the engine over a labelled dataset and reports, per
axis at an operating threshold, precision / recall / F1 / **false-positive rate / false-negative rate**
against two baselines: "no oversight" (predict nothing) and "flag everything" (predict all). ControlPlane
sits well inside both — on the current synthetic seed set, performance F1 0.83 (FPR 0.08, FNR 0.17) and
responsibility F1 0.89 (FPR 0.00, FNR 0.20), versus baselines at FNR 1.00 and FPR 1.00 respectively. It also
reports cost saved vs safety spend, percent cleared at T0, added latency, and each detector's calibration
error. The dataset is a clearly-labelled synthetic seed with deliberate hard cases; its two misses are
honest signposts — the missed name-only PII leak is what the NER detector (section 3) fixes, and the high
overconfidence calibration error is what the feedback loop (section 11) drives down. P3 swaps in labelled
public data behind the same interface. Run it with `make eval`; every number is regenerated, none hard-coded.

## 13. Known limitations (stated honestly)

- **Base-rate blind spot.** If every cheap T0 detector is silent (e.g. a calm, unhedged answer with no
  retrieved context), the axis probability starts near zero and the VoI rule may skip further checks. The
  fix is a per-axis prior base rate and cheap always-on detectors that do not need context; tracked in
  [DECISIONS.md](DECISIONS.md).
- **Heuristic detectors.** Today's detectors are lightweight stand-ins (lexical overlap, token-set
  disagreement, regex). They are honest T0 signals, not the model-based T1/T2 detectors they will become;
  every one documents its upgrade path.
- **Illustrative pricing.** The P&L uses placeholder model prices; real, sourced prices go in
  `docs/EVIDENCE.md` before any figure is published.
- **Reference decision / policy.** Action selection is a simple threshold reference; the full governance
  policy engine is P2's.

## 14. The Tower (proxy) and Control-Tower UI

The engine above is a library; **The Tower** ([`controlplane/proxy/`](../controlplane/proxy/)) is the inline
placement that makes it a product. It is a FastAPI app exposing an **OpenAI-compatible** `/v1/chat/completions`
(streaming and non-streaming) plus `/v1/models`, so any OpenAI client works with a one-line `base_url` swap.

Request path (`proxy/app.py` → `proxy/oversight.py`):

```
OpenAI request → upstream.generate() → OversightService.oversee():
   RequestContext → thermostat scrutiny → CascadeEngine.run() → PnlLedger.book()
   → actions.apply_action() (pass/annotate/auto-repair/redact/block) → recorder.record() → SSE fan-out
→ OpenAI-shaped response + a `controlplane` block (action, per-axis p_fail, net $, receipt id)
```

- **Upstream** (`proxy/upstream.py`). A deterministic, offline **failure-injecting** simulator by default
  (no keys, no downloads) that returns realistic support-bot/copilot traffic with planted failures and the
  RAG context to check against; a real multi-provider path via `litellm` turns on when a provider key is set.
- **Action layer** (`proxy/actions.py`). Where `AUTO_REPAIR` (deferred by `decision.py`) is honestly
  realized: a grounded correction from retrieved context when the model is probably wrong, deterministic PII
  redaction, or a block that never forwards the sensitive value. Everything else honours the engine's action.
- **Mid-stream abort** (`proxy/app.py::_stream_completion`). Streams tokens but holds back digit-bearing runs
  until they prove safe; a completed card/SSN triggers an abort so the leaked tokens never leave the server.
- **Oversight API + dashboard.** `/v1/oversight/{summary,receipts,stream,policy,simulate,replay}` feed the
  single-file Control-Tower UI (`proxy/static/index.html`): live SSE feed, the Oversight P&L, the
  confidently-wrong quadrant, the thermostat, and a click-into-any-receipt drawer with the full VoI trace.
- **Concurrency.** Detectors are pure and run outside a lock; only the mutating section (ledger totals,
  recorder hash chain, thermostat window, SSE fan-out) is serialized, so parallel requests can't corrupt the
  chain. Run it with `make serve`; drive it with `make traffic`.

## 15. Agentic trajectory oversight

An agent step is treated as *just another monitored call*, so the same `CascadeEngine` runs per step; the
auditor ([`controlplane/agent/auditor.py`](../controlplane/agent/auditor.py)) adds the signals that only exist
across steps and decides continue / escalate / abort:

- **compounding risk** — a running sum of per-step risk; crossing the policy `risk_budget` marks the run
  unrecoverable. We do *not* abort on the first blip (early errors often self-correct); we abort on the
  compounding one (the 2026 "unrecoverable vs first-error" finding).
- **loops** — the same tool called with the same arguments (`AgentStep.signature`) yields no new information;
  repeats above `loop_threshold` while uncertain trigger an abort. This is the clearest unrecoverable signal.
- **waste-killer** — aborting stops executing the remaining planned steps, so their token cost is never spent
  and is booked as `wasted_usd` saved (agent cost savings feeding the same self-funding P&L).

Each executed step is written to the flight recorder as an ordinary receipt (`use_case="agent"`), so agent
oversight shows up in the same live feed and audit trail. Endpoint: `POST /v1/oversight/agent-demo`; CLI:
`make agent`. The scripted trajectory ([`agent/scenarios.py`](../controlplane/agent/scenarios.py)) compounds a
hallucination and loops; the auditor aborts around step 2 and escalates, so the wrong answer never reaches the
user.

## 16. Layered safety detectors

Following the 2026 consensus that safety is a *stack* of distinct classifiers, the responsibility axis carries
three T0 detectors combined by the engine's noisy-OR: regex/Luhn **PII**, **prompt-injection** (an ingress
gate reading the prompt and any tool observations — indirect injection), and **unsafe-content** (an egress
moderation gate reading the response). All are honest heuristics with documented upgrades (PromptGuard-2,
Llama Guard 4 / ShieldGemma-2). See [`cascade/detectors/safety.py`](../controlplane/cascade/detectors/safety.py).

## 16b. Model-backed detectors + the T2 LLM-judge

Detectors are assembled by a factory ([`cascade/detectors/factory.py`](../controlplane/cascade/detectors/factory.py))
that probes the environment and picks the strongest available stack, so the same code runs offline (heuristics)
or upgraded (models) with no call-site changes:

- **Groundedness** — lexical T0 always; **HHEM-2.1-Open** cross-encoder at T1 when `transformers`/`torch` are
  installed (the VoI rule decides when to climb to it). `1 - factual_consistency` = groundedness risk.
- **PII** — regex T0 always; **Presidio NER** when opted in (`CONTROLPLANE_USE_PRESIDIO=1`).
- **T2 LLM-judge** ([`judge.py`](../controlplane/cascade/detectors/judge.py)) — a real, costly verification the
  stopping rule buys **only for the uncertain tail**. Backends auto-detected: litellm (a provider key) or a
  local **Ollama**. If neither is present the judge is absent and the cascade stops at T1 — no fabricated judge.
  Its real cost/latency feed the stopping rule and the P&L, so it embodies the VoI thesis end to end.

Every model-backed detector abstains (returns 0, flagged) on any load/inference failure, so enabling one can
never 500 a request. `GET /healthz` and the dashboard report which are live. Reproducibility: `make eval` and
the test suite pin heuristics-only (`CONTROLPLANE_MODELS=off`), so their numbers never depend on what happens
to be installed or listening locally. Prices are sourced in [EVIDENCE.md](EVIDENCE.md).

## 17. Compliance evidence pack

Regulations differ by geography/industry and evolve, so nothing about a rule is hard-coded in detection;
governance is policy-as-config and *evidence* is generated on demand from the tamper-evident receipts.
[`controlplane/compliance/pack.py`](../controlplane/compliance/pack.py) maps recorded facts (decision counts,
human escalations, blocks, chain-verification) onto concrete controls in the EU AI Act (Arts. 12/13/14/15/26/
50), ISO/IEC 42001, and NIST AI RMF, and renders an auditor-readable Markdown pack. It is an evidence aid, not
a certification — the disclaimer ships in every pack. Endpoints: `GET /v1/oversight/compliance[.md]`.
