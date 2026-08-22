# ControlPlane.ai — Round 2 Master Plan

Team **Hallucinators** · Accenture Innovation Challenge 2026 · Problem Track 1 (ControlPlane.ai)
Members: Nilakhya Mandita Bordoloi · Dhruv Tibarewal · Yugal Joshi — IIT Madras, Data Science & AI

> This is the single source of truth for R2. It reviews our R1 solution, locks the prototype scope,
> defines the architecture and the proof strategy, splits the work, and gives a day-by-day roadmap to
> the **30 Aug 2026 23:59 IST** deadline. Every claim we ship must be traceable to a primary source or a
> script that computes it. See `AI_CODING_GUIDELINES.md` for how we build and document.

---

## 0. North Star (read this first)

**One sentence:** ControlPlane is a real-time oversight layer that sits in front of *any* model and, for
*every* response, decides **how much verification that response is worth** — buying the cheapest signal
that could change the decision first, and letting the cost-axis savings *pay for* the safety checks.

**The wedge nobody else has productized:** oversight as a **value-of-information (VoI) decision under a
latency budget**. Existing tools *watch*, *guard*, *observe*, or *cut cost* — separately, after the fact,
with four different verdicts. We produce **one verdict across three coupled risks** (performance / cost /
responsibility) with an explicit economic stopping rule.

**The headline that wins the room:** *"Safer **and** cheaper — with a negative price tag."* The cost axis
is not a third thing to watch; its savings subsidise the other two. We will **prove** this with a
reproducible Oversight P&L and a counterfactual replay, not assert it.

**What "winning" looks like in the demo:** a judge says *"how is this different from Guardrails / NeMo /
Lakera / Arize?"* and we answer in one sentence; then we show a live P&L going net-negative and hit
**Replay** to show the exact same workload with oversight off — more failures reached users, more money
spent. That moment is the whole game.

---

## 1. Where we are & the hard deadline

| Stage | Window (IST) | What it needs | Status |
|---|---|---|---|
| R1 Solution Framework | 13–18 Aug | 2–3 slides + 2–3 min video | ✅ Passed (from ~1091 teams) |
| **R2 Prototype Development** | **21 Aug 16:00 → 30 Aug 23:59** | Public GitHub repo + working prototype + demo video + README (approach, architecture, deps, execution) | ⏳ **9 days — this plan** |
| Solution Discussion with AI | 21–30 Sep | Live AI-led technical deep-dive | After shortlist |
| Grand Finale (Bengaluru) | TBD | 10-min live demo + 5-min Q&A to jury | Top 10 only |

**Implication:** we optimise for a *thin but complete, provable* vertical slice by 30 Aug, then keep
hardening it through September for the AI discussion and finale. We do **not** build every moonshot now.

---

## 2. Honest review of our R1 solution

### What is genuinely strong (keep and double down)
- **The VoI framing** (`expected loss = P(failure) × Cost(failure)`, climb a tier only when expected-loss
  reduction beats the check's own cost+latency). This is the intellectual core and it is defensible.
- **Self-funding oversight** — a memorable, true-if-proven economic story that no incumbent leads with.
- **Three coupled risks, one verdict** — directly answers the brief and separates us from point tools.
- **Tri-detector tier table** (T0 free → T1 cheap → T2 costly/human) — clean, legible, maps to real tools.
- **Action layer** (pass / annotate / auto-repair / escalate / block / learn) — answers the brief's second
  explicit question and centers the human on the uncertain tail (matches Accenture's "humans in the lead").
- **The techniques named are real and current** (see `EVIDENCE.md` requirement): Semantic-Entropy
  Probes, MiniCheck, HHEM, GLiNER, RouteLLM, Llama Guard / ShieldGemma / PromptGuard-2, EU AI Act Art. 50.

### Risks to fix before R2 (do not ignore any of these)
1. **CRITICAL — unverifiable evidence.** The three "VERIFIED 2026 EVIDENCE" incidents (Meta Mar 2026 Sev-1,
   Uber budget exhausted, Stanford Jun 2026 26% bias) must each be backed by a primary, linkable source or
   **removed and replaced** with a verifiable public incident/paper. In an AI-led technical discussion and a
   jury Q&A, one fabricated stat destroys trust. → **P0 task, owner P3, gate before any slide/README ships.**
2. **Over-scoping.** The moonshot trio (Thermostat + Replay + Waste-killer) plus full compliance plus agentic
   demo is too much to *polish* in 9 days. We pick a spine (§5) and make it real; extras are additive, not
   load-bearing.
3. **Provability of the P&L.** The headline lives or dies on whether "cheaper" is *measured* against honest
   baselines, not asserted. The eval harness + replay (§9) is the credibility backbone, not a nice-to-have.
4. **"No ground truth" is the brief's hardest point.** Our production system must not depend on ground
   truth (it uses SEP / self-consistency / groundedness-vs-retrieved-context). Ground-truth labels appear
   **only in our offline evaluation** to measure detector quality — we must state this distinction explicitly.
5. **Latency claim.** "Doesn't slow the AI down" must be measured (p50/p95 added latency, % traffic that
   never leaves T0), not just argued from cited figures.

---

## 3. The winning thesis (sharpened)

We commit to five differentiators. Each is buildable in 9 days and each has a hero visual.

1. **VoI stopping rule as a real, calibrated controller.** `P(failure)` per axis is **calibrated**
   (isotonic/Platt on a held-out set) so the expected-loss math uses *honest* probabilities. We show a
   reliability diagram. This is the ML-depth flex and it directly tames the over/under-flagging tradeoff:
   we tune *one* expected-loss threshold, not a pile of per-detector hacks.
2. **Confidently-wrong quadrant** — a live 2D map (confidence × correctness); the high-confidence-and-wrong
   quadrant is the danger zone we exist to catch.
3. **Oversight P&L + counterfactual Replay** — the proof engine. Ledger of (cost saved − safety spend = net),
   and a one-click re-run of a recorded workload under a different policy/budget to show the counterfactual.
4. **Adaptive Oversight Thermostat** — a feedback controller that raises verification thoroughness when live
   risk spikes or budget allows, and relaxes when traffic is clean, so the safe majority is never slowed.
5. **VoI Receipt for every decision** — a human-readable record: which signals we bought, each one's ms + $,
   the expected-loss math, why we stopped, the action taken. This *is* the audit trail the brief asks for,
   and it feeds the compliance pack.

**Accenture-theme alignment ("Reinvent with AI. Put Humans in the Lead."):** humans decide the uncertain
high-stakes tail (escalate), every override teaches the system (learn), and every decision is auditable by a
human (receipts + compliance pack). AI does the tireless triage; humans keep the judgment.

---

## 4. Competitive landscape (have these answers ready)

| Category | Examples | What they do | Why we're different |
|---|---|---|---|
| Hallucination evals | Ragas, TruLens, DeepEval | Offline scoring of outputs | We decide *in real time* whether a check is even worth running |
| Guardrails | Guardrails AI, NeMo Guardrails, Lakera | Rule/classifier gates on I/O | One axis at a time, fixed cost per call; we make it an economic decision across 3 axes |
| Observability | Arize Phoenix, Fiddler, LangSmith | Dashboards + traces, post-hoc | We *act* inline (edit/escalate/block), not just observe |
| Cost/routing | Helicone, RouteLLM, Martian | Cut spend | We treat those savings as the *budget that funds safety* — the self-funding loop |
| Safety models | Llama Guard, ShieldGemma | Classify unsafe content | We *orchestrate* these under a VoI cascade instead of running the heaviest one on every call |

**One-liner for the panel:** *"Everyone else adds an oversight tax. We run oversight as a budget: the cost
axis pays for the safety axis, and we only spend on a check when it could change the decision."*

---

## 5. Prototype scope — MoSCoW (this is what we build)

**Philosophy (per team decision):** nothing here is out of scope. 9 days is enough to land the full spine
*and* iterate hard into the differentiators, and we keep adding through the Sep AI-discussion window. MoSCoW
is a **sequencing** tool, not a scope cut: P0 is the working spine we get running first, then we push
aggressively into P1 and P2 and keep iterating. The one hard rule that overrides everything else: **clarity
over cleverness — we ship only what all three of us can explain and justify.**

**P0 — MUST ship by 30 Aug (the load-bearing vertical slice):**
- OpenAI-compatible **proxy** ("The Tower") — one base-URL swap; streaming supported.
- **VoI tri-detector cascade** with real T0 + T1 per axis (T2 present as a real LLM-judge path, used sparingly):
  - Performance: self-consistency / semantic-entropy signal + groundedness-vs-retrieved-context (HHEM/MiniCheck).
  - Cost: model-overkill heuristic + semantic cache + router decision.
  - Responsibility: GLiNER PII + a safety/injection classifier.
- **Stopping rule + calibrated `P(fail)`** (the novel core).
- **Policy engine** with ≥2 use-case profiles (support-bot, internal-copilot) — pass/annotate/repair/escalate/block.
- **Flight recorder** — append-only, hash-chained log of every VoI receipt.
- **Oversight P&L ledger** (cost saved vs safety spend vs net).
- **Control-Tower UI v1** — live feed + P&L + drill-into-any-receipt + confidently-wrong quadrant.
- **Evaluation harness** — labeled failure-injection workload → per-axis P/R/F1/FPR/FNR, added latency, $ saved
  vs verify-all and verify-none baselines. **This is required, not optional.**
- **README** (approach, architecture, deps, one-command execution) + **2–3 min demo video** + public repo.

**P1 — SHOULD ship (the differentiators; each is high-leverage):**
- **Replay / What-If simulator** (re-run recorded workload under alternative policy/budget — proves the P&L).
- **Adaptive Oversight Thermostat** (feedback controller; demo by injecting a risk burst).
- **Compliance evidence pack** generator (maps receipts → EU AI Act Art. 50 / ISO 42001 / NIST AI RMF).
- **Mid-stream abort** on streaming (predict-and-stop a bad or looping generation).
- Calibration/reliability diagrams + ablations in the eval report.

**P2 — COULD ship if ahead of schedule (finale flavor):**
- **Agentic finale** — a tool-calling agent that loops/compounds a hallucination; trajectory audit + abort catches it.
- **Learning-from-overrides loop** — human escalations update the calibration set / thresholds.
- Third use-case profile (decision-support) to showcase multi-geo/risk governance.

**Deferred (we iterate toward these, not required for the first working slice):** production multi-tenant
auth, real customer data, horizontal scale-out, a trained-from-scratch model. For R2 we *simulate* enterprise
scale (tens of thousands of interactions) via the harness and say so honestly; real scale-out is a September
iteration target, not a hidden gap.

---

## 6. Demo narrative (the 3-minute story we are building toward)

1. **Swap one line** — point an app's `base_url` at ControlPlane. Nothing else changes.
2. **Live Tower** — traffic streams in across the two use-cases; most responses clear at T0 in milliseconds.
3. **Catch #1 (performance):** a support bot about to quote the wrong refund policy — groundedness probe
   catches it (~tens of ms, fraction of a cent), **auto-repaired** inline with the correct policy.
4. **Catch #2 (cost):** a query a GPT-4-class model was answering — **routed down** to a small model at equal
   quality; show the token/₹ delta.
5. **Catch #3 (responsibility):** a response leaking a customer's PII — **blocked**, receipt shows why.
6. **The P&L** — this window: cost-axis savings ₹X, safety+performance spend ₹Y, **net negative**.
7. **Don't trust it? → Replay** — same workload, oversight off: N failures reached users, ₹Z more spent.
8. **Every decision has a receipt** — open one; show the VoI math and the stopping reason.
9. **Compliance pack** — one click, auditor-ready evidence mapped to EU AI Act / ISO 42001 / NIST.
10. **Thermostat** — inject a burst of risky traffic; scrutiny automatically climbs, then relaxes — the safe
    97% is never slowed.

---

## 7. Architecture

### 7.1 System view
```
App / Agent ──base_url swap──▶  CONTROLPLANE ("The Tower")
                                  │
        INGRESS GUARDS ──────────▶│  prompt-injection · inbound PII
                                  │
        TRI-DETECTOR CASCADE ────▶│  VoI: T0 → T1 → T2 per axis, run in parallel, + mid-stream abort
          ├─ Performance          │     (self-consistency / SEP · groundedness HHEM/MiniCheck · judge)
          ├─ Cost                 │     (overkill · semantic cache · router · trajectory audit)
          └─ Responsibility       │     (GLiNER PII · safety/bias · Llama-Guard-class review)
                                  │
        STOPPING RULE + CALIB ───▶│  expected_loss = P(fail)·Cost(fail); stop when Δloss < check cost
                                  │
        POLICY ENGINE ───────────▶│  pass · annotate · auto-repair · escalate · block  (per use-case/geo/risk)
                                  │
        FLIGHT RECORDER ─────────▶│  every VoI receipt → append-only, hash-chained log
                                  │
        ├─ CONTROL-TOWER UI       │  live fleet · P&L · incidents · drill-in · confidently-wrong quadrant
        ├─ REPLAY / WHAT-IF       │  re-run recorded workload under alt policy/budget → counterfactual $ & failures
        └─ COMPLIANCE EXPORT      │  EU AI Act Art.50 · ISO 42001 · NIST AI RMF evidence pack
```

### 7.2 Repo layout
```
controlplane/
  README.md  PLAN.md  AI_CODING_GUIDELINES.md
  pyproject.toml            # pinned deps
  docker-compose.yml  .env.example
  controlplane/             # python package
    proxy/                  # FastAPI OpenAI-compatible gateway, streaming, mid-stream abort   [P2]
    cascade/
      engine.py             # tier orchestration + parallel detector execution                [P1]
      voi.py                # expected-loss math, calibration, stopping rule                   [P1]
      thermostat.py         # adaptive controller                                             [P1]
      detectors/{base,performance,cost,responsibility}.py                                      [P1]
    policy/                 # config schema, hot-reload, per use-case/geo/risk profiles        [P2]
    recorder/               # sqlite + hash-chain store, receipt builder                        [P2/P1]
    pnl/                    # pricing tables + P&L ledger                                        [P1]
    replay/                 # what-if simulator                                                 [P1]
    compliance/             # evidence-pack generator                                           [P3]
    eval/                   # inject.py, run.py, metrics.py, report.py, baselines                [P2/P3]
  ui/                       # Control Tower (Next.js hero; Streamlit fallback)                   [P3/P1]
  data/                     # dataset fetch scripts (large files gitignored)                     [P3]
  tests/                    # unit tests, esp. voi/stopping-rule math                            [all]
                       # ARCHITECTURE.md · DECISIONS.md (ADRs) · EVIDENCE.md                [all]
```

### 7.3 The integration contract — VoI Receipt (define Day 1, freeze it)
Everyone builds against this JSON so the three of us work in parallel without blocking:
```jsonc
{
  "request_id": "uuid",
  "use_case": "support_bot",
  "ts": "2026-08-24T10:00:00Z",
  "signals": [
    {"name": "hhem_groundedness", "axis": "performance", "tier": 1,
     "score": 0.31, "p_fail_calibrated": 0.62, "cost_usd": 0.0002, "latency_ms": 41}
  ],
  "expected_loss_before": 0.90, "expected_loss_after": 0.12,
  "stopping_reason": "delta_loss_below_next_check_cost",
  "action": "auto_repair",                // pass|annotate|auto_repair|escalate|block
  "repaired_output": "…",                 // nullable
  "pnl": {"cost_saved_usd": 0.011, "safety_spend_usd": 0.0004, "net_usd": -0.0106},
  "policy_id": "support_bot@IN@balanced",
  "hash_prev": "…", "hash_self": "…"      // tamper-evident chain
}
```

---

## 8. Detection & decision internals

- **Performance axis.** Cheap first: sampled self-consistency + semantic clustering (embeddings/NLI) as a
  black-box uncertainty signal; groundedness against retrieved context via **HHEM-2.1-Open** or **MiniCheck**
  when the call is RAG. White-box **Semantic-Entropy-Probe**-style overconfidence is demoed on the one path
  where we serve a local open-weights model (Ollama/vLLM) and can read hidden states — we are explicit that
  API models only expose I/O, per the brief.
- **Cost axis.** Model-overkill heuristic (short/lookup-style prompts don't need the flagship), **semantic
  cache** (embed → cosine hit), **router** (RouteLLM-style or a small learned/heuristic router), and an
  **agent-trajectory audit** for loops/dead-ends. Savings are metered in tokens → ₹ via a pricing table.
- **Responsibility axis.** **GLiNER** zero-shot PII/entities + Presidio fallback; a lightweight safety/
  prompt-injection classifier at T1; a Llama-Guard-class check or human review at T2 for the high-stakes tail.
- **Calibration.** Each axis emits a raw score; we fit isotonic/Platt on a held-out labeled split so
  `P(fail)` is honest. Reliability diagrams go in the eval report.
- **Stopping rule.** Maintain current `expected_loss = P(fail)·Cost(fail)`. Only climb to the next tier when
  the *expected reduction in loss* from that tier exceeds the tier's own `cost_usd + λ·latency_ms`. λ (the
  latency price) and `Cost(fail)` come from the active policy profile → this is how one knob tunes the whole
  over/under-flagging tradeoff per use-case.
- **Thermostat.** A feedback controller over a sliding window of recent risk + remaining budget nudges the
  per-axis tier thresholds up under stress and down when clean. Simple, legible, and visually great.

---

## 9. Evaluation & proof strategy (the credibility backbone)

This is what separates "nice dashboard" from "these people did real work." Owner: **P2** (harness) + **P3**
(data) + **P1** (metrics/calibration).

- **Labeled workload via failure injection.** Assemble from public, license-checked datasets and inject
  labeled failures across all three axes:
  - Hallucination / groundedness: HaluEval, RAGTruth, or a FActScore-style set (+ MiniCheck's benchmarks).
  - PII / privacy: synthetic PII insertion into otherwise-clean responses (labeled spans).
  - Safety / bias: a public red-team / bias subset (license-checked).
  - Cost: real token counts + a documented price table; router decisions logged.
  - Overconfidence: paired correct/incorrect answers with model confidence to populate the quadrant.
  Ground-truth labels exist **only here, for measuring detector quality** — the live system never sees them.
- **Baselines (mandatory):** *verify-none* (raw model) and *verify-all* (heaviest checks on every call). We
  report where ControlPlane lands between them on quality, latency, and cost — the whole point is dominating
  the tradeoff curve.
- **Metrics:** per-axis Precision / Recall / F1 / **FPR / FNR** (directly answers the brief's "report FP/FN to
  a skeptical stakeholder"); added latency p50/p95; % traffic resolved at T0; $ saved vs both baselines; net
  P&L; calibration (ECE + reliability diagram).
- **Ablations:** cascade vs always-T2 (keeps quality, cuts cost/latency); with/without thermostat; with/without
  cache/router.
- **Reproducibility:** fixed seeds, pinned deps, one command (`make eval`) regenerates every number in the
  README and slides. **No number appears anywhere unless this command produces it or `EVIDENCE.md` links a
  primary source.**

---

## 10. Tech stack & key decisions (ADRs live in `DECISIONS.md`)

- **Language:** Python (team preference). Backend concurrency via `asyncio` so detectors run in parallel to
  protect latency (this *is* the brief's "checks run in parallel" point — make it real).
- **Proxy:** FastAPI exposing OpenAI-compatible endpoints, using the `litellm` SDK for multi-provider fan-out
  (OpenAI/Anthropic/Bedrock/OSS) → the genuine one-line base-URL swap.
- **Models:** at least one **local open-weights** model via **Ollama** (for white-box SEP/overconfidence and
  for cheap routing targets) + one hosted API model for the "flagship" tier.
- **Detectors:** `gliner`, `presidio`, HHEM-2.1-Open / MiniCheck (HF), a small safety/injection classifier,
  embeddings (e.g. `bge-small`) + FAISS/numpy for cache & semantic clustering.
- **Storage:** SQLite for the flight recorder with a SHA-256 hash chain (honestly "tamper-evident," not
  "immutable ledger" — we say what it actually is).
- **UI (decision):** **Next.js + Tailwind + shadcn/ui + Recharts** for the hero Control Tower (the visual that
  wins the finale). **Streamlit is the explicit fallback** for the eval dashboard and if front-end time runs
  short. Go/no-go on Next.js checkpoint: **Day 4** — if the React path is behind, ship Streamlit and keep the
  polish budget for the demo.
- **Packaging:** `pyproject.toml` with pinned versions; `docker-compose up` brings the whole stack; `.env.example`
  documents keys; `make demo` and `make eval` are the two blessed entry points.

---

## 11. Work division

Principle: **P1 owns the brain end-to-end; P2 owns the platform/system-design in Python; P3 owns bounded
buildable pieces + the deliverables.** Everyone writes code and everyone can explain any code with their name
on it (enforced in review — see `AI_CODING_GUIDELINES.md`).

### P1 — Core / VoI engine (owns the intellectual core, integrates everything)
- Cascade engine + parallel detector orchestration (`cascade/engine.py`).
- VoI math: expected-loss, **calibration**, **stopping rule** (`cascade/voi.py`).
- Detector implementations & wiring (`cascade/detectors/*`): self-consistency/SEP, groundedness, PII/safety, router, cache.
- **Thermostat** controller, **P&L ledger** + pricing, **Replay/What-If** simulator, **VoI receipt** builder.
- Overall architecture, integration, and the demo storyline.
- **Acceptance:** end-to-end a request produces a correct receipt; stopping rule provably reduces cost vs
  verify-all at ≥ equal caught-failure rate on the eval set; calibration ECE reported; replay reproduces the P&L.

### P2 — Platform / systems (Java/Spring instincts → applied in Python)
- FastAPI **proxy** (OpenAI-compatible, **streaming**, mid-stream-abort plumbing) — `proxy/*`.
- **Flight recorder**: SQLite + hash-chain, append-only, query API — `recorder/store.py`.
- **Policy engine**: config schema, validation, hot-reload, per use-case/geo/risk profiles — `policy/*`.
- Concurrency model (asyncio, timeouts, parallel detectors, backpressure) and latency budget enforcement.
- **Eval harness runner** + baselines + metrics computation — `eval/run.py`, `eval/metrics.py`.
- **Dockerization** + one-command setup + the "execution instructions" half of the README.
- **Acceptance:** `docker-compose up` yields a working proxy; streaming + abort demonstrated; policy hot-reload
  works; `make eval` runs the harness and emits the metrics table + baselines.

### P3 — Data, UI build, compliance, and deliverables
- **Evidence verification (P0, first):** fact-check every cited statistic; produce `EVIDENCE.md` with a
  primary link per claim; flag anything unverifiable for replacement. **Gate before any slide/README ships.**
- **Failure-injection dataset**: fetch + license-check public datasets, write labeled injection scripts —
  `eval/inject.py`, `data/`.
- **Control-Tower UI** build (with P1's API + component support; Streamlit fallback) — `ui/`.
- **Compliance evidence-pack** generator (mapping table + template → markdown/PDF) — `compliance/*`.
- **Deliverables:** README polish, 2–3 min **demo video**, finale slides, screen-recording of the live demo.
- **Acceptance:** UI renders live feed + P&L + drill-in from the recorder; `EVIDENCE.md` has zero unverifiable
  claims; compliance pack generates from real receipts; video is cut and under time.

> **Confirmed mapping:** P1 = **Dhruv** (heaviest core, VoI engine + integration), P2 = **Yugal** (platform/
> systems), P3 = **Nilakhya** (data + UI + compliance + deliverables). Full task-level breakdown, acceptance
> criteria, dependencies, and "explain-back" topics live in `WORKPLAN.md`. In a swarm where everyone can do
> everything, these are *ownership* boundaries (who is accountable), not walls — overflow rules in `WORKPLAN.md`.

---

## 12. Day-by-day roadmap (Aug 21 → Aug 30)

| Day | Date | Goal | Key outputs |
|---|---|---|---|
| 0–1 | Aug 21–22 | Scaffold + contracts + evidence audit | Repo skeleton, pinned deps, **VoI-receipt schema frozen**, FastAPI proxy passthrough working end-to-end (no-op cascade), datasets chosen & license-checked, `EVIDENCE.md` started, demo domain locked (support-bot primary + copilot secondary) |
| 2–3 | Aug 23–24 | Vertical slice | Real T0+T1 detectors per axis, flight recorder writing receipts, policy engine v1 (2 profiles), first eval run with a metrics table + baselines |
| 4–5 | Aug 25–26 | The novel core + hero visuals | Stopping rule + calibration, P&L ledger + receipts, Control-Tower UI v1 (live feed + P&L + drill-in + quadrant), Replay/What-If v1. **UI framework go/no-go (Day 4).** |
| 6 | Aug 27 | Differentiators | Thermostat, compliance export, mid-stream abort, third policy profile / (stretch) agent finale |
| 7 | Aug 28 | **Feature freeze** + proof | Full eval run + ablations + calibration diagrams; **demo dry-run #1 recorded & critiqued**; bug triage |
| 8 | Aug 29 | Polish + package | UI polish, README (approach+arch+deps+**one-command run**), record demo video, slides, Docker reproducibility, `make demo`/`make eval` verified on a clean clone |
| 9 | Aug 30 | Buffer + ship | Demo dry-run #2, final video edit, **make repo public**, submit **with margin before 23:59 IST** |

Rule: if a day slips, we cut from **P2/COULD first**, never from P0. The vertical slice and the eval harness
are sacred.

---

## 13. Coordination & workflow

- **Repo:** `github.com/dhruv-decoder/Hallucinators` — **private during build, public at submission**. Do not
  commit secrets; `.env` is gitignored, `.env.example` documents keys.
- **Branching:** `main` always runnable; feature branches → PR → **P1 reviews & merges**. Small PRs (< ~400
  lines) so reviews are real.
- **Contracts first:** the VoI-receipt schema (§7.3) and the `Detector` base interface are frozen Day 1 so all
  three work in parallel against stable seams.
- **Daily 15-min async standup** (shared channel): yesterday / today / blockers. A short `STATUS.md` or GitHub
  Projects board tracks task state.
- **Definition of Done** (every task): code + docstrings + a test where logic is non-trivial + it runs from a
  clean clone + the author can explain it live.
- **Two recorded dry-runs** (Day 7, Day 9) — we watch them back and cut whatever doesn't land in 3 minutes.
- **Stay in the loop (non-negotiable):** AI writes a lot of this code; the owner of each module reads every
  line, can defend it in the AI discussion, and rewrites anything they can't explain. Follow
  `AI_CODING_GUIDELINES.md`.

---

## 14. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Unverifiable evidence in slides/README | Credibility collapse in Q&A | P0 `EVIDENCE.md` gate; every stat linked or from `make eval` |
| Over-scoping → nothing polished | Weak demo | MoSCoW; P0 slice sacred; cut from COULD first |
| P&L looks made-up | Loses the headline | Replay counterfactual + baselines + reproducible `make eval` |
| Latency claim unproven | "Does it actually stay fast?" | Measure p50/p95 added latency + %-cleared-at-T0; show it live |
| Front-end eats the schedule | No brain finished | Streamlit fallback; Day-4 go/no-go; UI consumes a stable API |
| Detector accuracy weak on our data | Bad metrics table | Calibrate + report honestly; the *decision framework* is the contribution, not raw detector SOTA |
| Someone can't explain AI-written code | Fails the AI discussion | DoD "explain-back"; owner rewrites unclear code |
| Dataset licensing | Can't publish repo | License-check every dataset Day 1; scripts fetch, large files gitignored |

---

## 15. R2 submission checklist (all required by 30 Aug 23:59 IST)

- [ ] Public GitHub repo (source + pinned deps + config).
- [ ] `README.md`: solution approach, **architecture**, implementation, key features, **dependencies**, **execution instructions** (one command).
- [ ] Working prototype: `docker-compose up` → proxy + UI; `make demo` runs the scripted demo; `make eval` regenerates metrics.
- [ ] 2–3 min prototype **demo video** (MP4/MOV).
- [ ] `EVIDENCE.md` — every external claim sourced; zero unverifiable stats.
- [ ] Naming convention respected: **TeamName_CampusName** (`Hallucinators_IITMadras`).
- [ ] Eval report (metrics table, baselines, ablations, calibration) reproducible from `make eval`.

---

## 16. Open decisions to confirm (defaults chosen; override if needed)

1. ~~**Demo domain**~~ → **RESOLVED: support-bot RAG primary, with the agentic workflow designed in as a
   first-class extension** (the cascade, recorder, and policy engine treat an "agent turn" as just another
   monitored call, so extending to trajectory-audit/mid-stream-abort is additive, not a rewrite).
2. **UI:** default **Next.js hero + Streamlit fallback**, Day-4 go/no-go. (Confirm React appetite when we get there.)
3. ~~**P2/P3 name mapping**~~ → **RESOLVED: P1 = Dhruv, P2 = Yugal, P3 = Nilakhya** (see §11 / `WORKPLAN.md`).
4. **Evidence:** live web-verification pass on the three R1 incidents is **P3's first task** (`EVIDENCE.md`),
   gating any reuse of those slides. Not blocking the build; blocking the *claims*.

---
*This plan is deliberately biased toward a provable vertical slice over breadth. We win by making the
economic decision rule real and by proving "safer and cheaper" with numbers anyone can reproduce.*
