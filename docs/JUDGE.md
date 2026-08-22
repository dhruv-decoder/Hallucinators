# JUDGE.md — R2 Proposal Decoded + Honest Self-Scorecard

Purpose: turn the Round-2 brief (`r2.md`) and the competition rules (`info.md`) into an explicit rubric, then
**rate our own solution critically and honestly** against it — so we always know how much we're actually
covering vs. what still needs work. Update the scores at every dry-run and before submission. Be harsh here so
the jury can't be.

**Scale:** 0 = absent · 1 = named only · 2 = designed · 3 = partially built · 4 = built & working · 5 = built,
measured, and defensible. We track two columns: **Design** (how well the plan covers it) and **Built** (what
actually runs today). Right now most Built scores are 0 — that's expected at plan stage; this file is the
burn-down.

---

## PART 1 — The R2 proposal, decoded (what they're really asking)

The R2 brief keeps ControlPlane **intentionally open** ("no single correct architecture… make reasonable
assumptions… focus on innovation, creativity, technical novelty"). It gives three lenses:

**A. Real-world complexities they want us to grapple with** (each is a scoring axis — if we ignore one, a
judge will ask about it):
1. **Different use cases → different risk tolerance & latency budgets.** One-size checking fails. → our
   per-use-case policy profiles + VoI budget answer this directly.
2. **Bias / hallucination / privacy overlap.** A fabricated detail about a person is *both* a hallucination
   and a privacy leak. Clean categorization is hard. → our "one verdict, three coupled axes" is literally this
   point; we must show a case that trips two axes at once.
3. **No reliable real-time ground truth.** The gaps that cause hallucination also block automated verification.
   → our black-box uncertainty (self-consistency / semantic entropy) + groundedness-vs-retrieved-context; we
   must be explicit that ground-truth labels live only in *our offline eval*, never in the live system.
4. **Over-flag (alert fatigue) vs under-flag (liability).** Real systems *tune* this, not solve it. → our
   single calibrated expected-loss threshold is the tuning knob; show the ROC/precision-recall trade we chose.
5. **Multi-turn & agents compound risk.** One bad output shapes many downstream decisions. → trajectory audit
   + mid-stream abort; the agentic extension we designed in.
6. **Regulations differ by geo/industry and evolve.** Rigid hard-coded rules age. → policy-as-config +
   compliance pack; nothing about a rule is hard-coded in code.
7. **Enterprises consume the FM via API → limited internal inspection.** Mostly I/O-layer. → we work at I/O by
   default and are explicit that white-box SEP is only available on the one path where we host an open model.

**B. Solutioning areas we may draw from** (the checklist they'll mentally tick):
- **Detection:** heuristics · embedding/statistical anomaly · AI-as-judge · retrieval verification · PII/entity.
- **Decision logic:** confidence scoring · tiered responses (allow/edit/flag/block) · when a human is pulled in.
- **Architecture:** where the checker sits (pre-response gate / inline middleware / post-hoc audit) · parallel checks.
- **Governance:** configurable policy by use-case/geo/risk · audit trail behind every decision.
- **Feedback loops:** flagged/overridden cases improve detection over time.
- **Metrics & monitoring:** FP/FN rates · overall trustworthiness reported to a *skeptical stakeholder*.

**C. Reference parameters (illustrative):** an enterprise running *multiple* AI use cases at once (support
assistant + internal knowledge assistant + decision-support), each with different latency/risk tolerance;
**tens of thousands of interactions/week**; a mix of well- and loosely-governed data sources. → we simulate
exactly this shape in the harness and say the numbers are simulated.

**What R2 explicitly rewards** (from `info.md`): a working prototype demonstrating **practicality,
scalability, and impact**; README (approach, architecture, implementation, key features); demo video; public
repo. The later **AI discussion** grades: technical & AI proficiency · tech-stack expertise · problem-solving ·
solution thinking · **innovative approach** · depth of understanding of the problem. The theme throughout:
**"Reinvent with AI, put humans in the lead," value at scale.**

**Reading of what wins:** breadth of the checklist is table stakes; the *differentiator* is a **genuinely novel
mechanism that's actually built and measured**. Our VoI economic decision rule + self-funding P&L is that
mechanism. The risk is being long on narrative and short on proof — this scorecard exists to stop that.

---

## PART 2 — Scorecard (weighted, honest)

| # | Criterion (source) | Wt | Design | Built | Notes / what "5" needs |
|---|---|---:|:--:|:--:|---|
| 1 | **Problem understanding & fit** to ControlPlane brief (A1–A7) | 6 | 5 | 3 | Demo handles perf/cost/responsibility live. "5" = a two-axis-at-once case (A2) shown explicitly. |
| 2 | **Detection breadth & depth** (B: heuristics, anomaly, judge, retrieval, PII) | 9 | 4 | 2 | T0 heuristics for all axes run. Need model-based T1/T2 (HHEM/GLiNER/judge) + measured P/R. |
| 3 | **Decision logic** (confidence scoring, tiered allow/edit/flag/block, human-in-loop) | 9 | 5 | 4 | VoI stopping rule + calibrated tiers + escalate/block all firing in the demo. "5" = AUTO_REPAIR wired. |
| 4 | **Architecture** (placement, inline, parallel-for-latency) | 6 | 4 | 2 | Engine built; inline proxy + parallel async are P2's next. "5" = measured p50/p95 added latency. |
| 5 | **Governance** (policy by use-case/geo/risk, audit trail) | 6 | 4 | 2 | PolicyProfile + hash-chained receipts built; hot-reload + multi-profile pending (P2). |
| 6 | **Feedback loops** (learning from overrides) | 4 | 2 | 0 | Still the weakest. Ship override → recalibrate (P1 has calibration ready to reuse). |
| 7 | **Metrics & monitoring** (FP/FN, trustworthiness to a skeptic, reproducible) | 9 | 4 | 1 | Calibration + ECE exist; the eval harness + baselines are the next big lift (P2 runner, P3 data). |
| 8 | **Hard complexities handled** (no ground truth, risk overlap, over/under-flag, multi-turn/agents, evolving regs, API-only) | 10 | 4 | 3 | No-ground-truth (self-consistency), over/under-flag (VoI knobs), API-only (I/O) all coded. Multi-turn/agent pending. |
| 9 | **Innovation / novelty / differentiation** (VoI, self-funding, thermostat, replay, receipts) | 10 | 5 | 4 | VoI + self-funding P&L + receipts run live and net negative. "5" = Replay + Thermostat shipped. |
| 10 | **Technical depth & AI proficiency** (for the AI discussion) | 8 | 4 | 3 | Calibration + VoI implemented and tested from scratch. "5" = each member can defend it live. |
| 11 | **Tech-stack expertise & engineering quality** | 5 | 3 | 4 | Typed, 20 tests green, lint-clean, one-command run, pinned deps, no dead code. |
| 12 | **Practicality, scalability & measurable impact** (R2 explicit) | 7 | 3 | 2 | Demo runs; scale still simulated small. "5" = throughput/latency + a labelled at-scale ₹ extrapolation. |
| 13 | **Accenture theme: humans-in-the-lead, value at scale** | 4 | 4 | 2 | Escalate action + auditor receipts built. "5" = override-learning loop + narrated in the video. |
| 14 | **Deliverable quality** (prototype runs, README, video, public repo) | 4 | 2 | 2 | Runs from a clean clone (`make demo`), README + public repo done. Missing: demo video + eval numbers. |
| 15 | **Evidence integrity / credibility** (no fabricated claims) | 3 | 2 | 2 | Three R1 incidents confirmed by the team; now must be *documented with links* in `EVIDENCE.md`, and the illustrative P&L prices replaced with sourced ones. "5" = every published number has a link or a `make eval` source. |

**Weighted snapshot (updated after the P1 engine build):** Design readiness ≈ **78%**; Built readiness ≈
**~51%** of max (was ~2% at plan stage). Interpretation: *the decision engine — our differentiator — is
built, tested, and demonstrably self-funding, which is the hard part. The remaining lift is proof and
surface: the eval harness with real FP/FN numbers (#7), model-based detectors (#2), the proxy + UI so it
looks like a product (#4, deliverables), the feedback loop (#6, still 0), and documenting evidence (#15).*

*(Recompute the % whenever scores change: weighted mean of the column ÷ 5. Keep it honest — if it's not
measured or not runnable, it's not a 4+.)*

---

## PART 3 — Biggest gaps → concrete actions (attack these)

1. **#15 Evidence integrity (highest urgency).** P3 produces `EVIDENCE.md`; every external stat linked to
   a primary source or replaced. Gate on all slides/README. *Until done, we assume our own numbers are wrong.*
2. **#7/#9 Proof of "safer AND cheaper."** The eval harness + Replay must produce reproducible baselines; the
   P&L must be a computed number, not a picture. This is what converts novelty into a defensible claim.
3. **#6 Feedback loop.** Upgrade from a sketch to a working "override → update calibration set → re-fit" path,
   even if simple. It's a named brief area we're currently weak on.
4. **#8/A5 Multi-turn & agents.** Land at least one agentic demo (loop caught by trajectory audit + abort) so we
   can answer the compounding-risk question with a demo, not a promise.
5. **#12 Scalability story.** Prepare an honest throughput/latency measurement + a clearly-labeled at-scale
   extrapolation (tens of thousands/week → ₹ impact). Never present simulated numbers as production numbers.

## PART 4 — Questions the AI panel will likely ask (rehearse answers)
- "How is this different from Guardrails / NeMo / Lakera / Arize?" → `PLAN.md` §4 one-liner.
- "With no ground truth, how do you know a claim is wrong?" → self-consistency / semantic entropy + groundedness; ground truth only in offline eval.
- "How do you avoid alert fatigue?" → one calibrated expected-loss threshold; show the chosen precision/recall point.
- "Prove it's actually cheaper." → live P&L + Replay counterfactual + `make eval` baselines.
- "Does the checker slow the model down?" → measured p50/p95 added latency + %-cleared-at-T0; parallel async.
- "What happens with agents / multi-turn?" → trajectory audit + mid-stream abort demo.
- "How does this comply with regulation X?" → policy-as-config + the generated compliance pack.
- "What are your false-negative risks?" → honest FP/FN table + the limitations section; escalation covers the tail.

> Rule: if we can't point at a file, a number from `make eval`, or a live demo moment for a criterion, its
> Built score is not 4+. Keep this file brutally honest — it's our early-warning system.
