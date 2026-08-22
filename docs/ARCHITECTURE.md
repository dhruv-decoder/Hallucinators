# Architecture

How the ControlPlane oversight engine works, end to end. This describes what is implemented today (the
decision engine); the proxy, richer detectors, UI, and replay simulator are tracked in [PLAN.md](PLAN.md).

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
- **Responsibility** (failure-type): biased, unsafe, leaking. Detectors: regex/Luhn PII (T0). Upgrades:
  GLiNER/Presidio, safety classifiers, Llama-Guard-class review.
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

## 9. Known limitations (stated honestly)

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
