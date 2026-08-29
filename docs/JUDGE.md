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
| 1 | **Problem understanding & fit** to ControlPlane brief (A1–A7) | 6 | 5 | 4 | Handles perf/cost/responsibility live, incl. a two-axis-at-once case (A2), agents (A5), and API-only (A7). "5" = shown in the demo video. |
| 2 | **Detection breadth & depth** (B: heuristics, anomaly, judge, retrieval, PII) | 9 | 5 | 4 | T0 heuristics all axes + Presidio NER + **HHEM-2.1 groundedness (measured F1 0.76 on real HaluEval)** + prompt-injection/unsafe + **a real T2 LLM-judge**. "5" = larger-n CI + more axes on public data. |
| 3 | **Decision logic** (confidence scoring, tiered allow/edit/flag/block, human-in-loop) | 9 | 5 | 5 | VoI stopping rule + calibration + pass/annotate/**auto-repair**/escalate/block all firing inline; judge climbed to only on the tail. |
| 4 | **Architecture** (placement, inline, parallel-for-latency) | 6 | 5 | 5 | Inline OpenAI-compatible proxy (streaming + mid-stream abort) + **measured p50 0.12ms / p95 0.16ms added latency, ~7,100 rps**. |
| 5 | **Governance** (policy by use-case/geo/risk, audit trail) | 6 | 5 | 4 | Policy profiles + hash-chained receipts + **compliance evidence pack** (EU AI Act/ISO 42001/NIST). "5" = config hot-reload + more geo profiles (P2). |
| 6 | **Feedback loops** (learning from overrides) | 4 | 3 | 3 | Human overrides refit detector calibration (demo cuts ECE 0.40->0.01). "5" = wired into the live override UI + threshold learning. |
| 7 | **Metrics & monitoring** (FP/FN, trustworthiness to a skeptic, reproducible) | 9 | 5 | 4 | Per-axis P/R/F1/FPR/FNR vs baselines + ECE on synthetic **and real HaluEval** (`make eval-real`), reproducible. "5" = larger-n with confidence intervals. |
| 8 | **Hard complexities handled** (no ground truth, risk overlap, over/under-flag, multi-turn/agents, evolving regs, API-only) | 10 | 5 | 4 | No-ground-truth (self-consistency/HHEM), overlap (2-axis case), over/under-flag (VoI knobs), **multi-turn/agents (trajectory auditor)**, evolving regs (policy-as-config + compliance), API-only (I/O). |
| 9 | **Innovation / novelty / differentiation** (VoI, self-funding, thermostat, replay, receipts) | 10 | 5 | 5 | VoI + self-funding P&L + receipts + Replay + Thermostat + **agent waste-killer** + VoI-gated judge — shipped and tested. |
| 10 | **Technical depth & AI proficiency** (for the AI discussion) | 8 | 5 | 4 | Calibration + VoI from scratch; cascade provably climbs to a model on the uncertain tail; measured lift on real data. "5" = each member defends it live. |
| 11 | **Tech-stack expertise & engineering quality** | 5 | 5 | 5 | 73 tests green, lint-clean, typed; **Next.js/TS/Tailwind frontend + FastAPI backend**, pinned deps + lockfiles, Docker/Render, one-command run. |
| 12 | **Practicality, scalability & measurable impact** (R2 explicit) | 7 | 4 | 4 | Measured p95 0.16ms + ~7,100 rps + 100% cleared@T0 + at-scale $ extrapolation. "5" = multi-tenant + real-provider load test. |
| 13 | **Accenture theme: humans-in-the-lead, value at scale** | 4 | 5 | 4 | Escalate + auditor receipts + override-learning + agent abort→human, all in a real UI. "5" = narrated in the video. |
| 14 | **Deliverable quality** (prototype runs, README, video, public repo) | 4 | 4 | 4 | Runs from a clean clone, README + WALKTHROUGH + DEPLOY + public repo + deployable (Render/Vercel). Missing: the demo video. |
| 15 | **Evidence integrity / credibility** (no fabricated claims) | 3 | 4 | 4 | Prices sourced + measured results in `EVIDENCE.md`; a real env bug (transformers 5.x) found & documented. "5" = replace/verify the three R1 incidents. |

**Weighted snapshot (updated after the proxy + UI + agents + compliance + model detectors + real-data eval + Next.js frontend):**
Design readiness ≈ **95%**; Built readiness ≈ **~88%** of max (was ~2% at plan stage, ~62% after the eval
harness). Interpretation: *the full vertical slice is now real and measured — inline OpenAI-compatible proxy
with auto-repair/redaction/mid-stream abort, a modern Next.js/TS/Tailwind Control-Tower, agentic trajectory
oversight, model-backed groundedness (HHEM, F1 0.30→0.76 on real HaluEval), a VoI-gated T2 judge (Groq/Ollama),
a compliance evidence pack, and a measured latency/scale benchmark (p95 0.16ms, ~7,100 rps). The remaining lift
is now almost entirely deliverables and hardening: the **demo video** (#14), **verifying/replacing the three R1
incidents** (#15, the last credibility gap), **config hot-reload + multi-tenant** (#5/#12), and **wiring
override-learning into the live UI** (#6).*

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
- "How is this different from Guardrails / NeMo / Lakera / Arize?" → those watch, guard, or observe separately and after the fact; ControlPlane runs one VoI-gated verdict across performance, cost, and responsibility, with a conformal guarantee and a self-funding P&L.
- "With no ground truth, how do you know a claim is wrong?" → self-consistency / semantic entropy + groundedness; ground truth only in offline eval.
- "How do you avoid alert fatigue?" → one calibrated expected-loss threshold; show the chosen precision/recall point.
- "Prove it's actually cheaper." → live P&L + Replay counterfactual + `make eval` baselines.
- "Does the checker slow the model down?" → measured p50/p95 added latency + %-cleared-at-T0; parallel async.
- "What happens with agents / multi-turn?" → trajectory audit + mid-stream abort demo.
- "How does this comply with regulation X?" → policy-as-config + the generated compliance pack.
- "What are your false-negative risks?" → honest FP/FN table + the limitations section; escalation covers the tail.

> Rule: if we can't point at a file, a number from `make eval`, or a live demo moment for a criterion, its
> Built score is not 4+. Keep this file brutally honest — it's our early-warning system.
