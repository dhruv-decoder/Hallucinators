# WORKPLAN — 3-Way Division & Execution

Team **Hallucinators**. Companion to `PLAN.md` (scope/architecture) and `AI_CODING_GUIDELINES.md` (how we
build). This doc says **who owns what, in what order, and how we work in parallel without colliding.**

- **P1 — Dhruv** — VoI engine / the brain + integration (**heaviest load, the intellectual core**).
- **P2 — Yugal** — platform & systems (proxy, recorder, policy, eval-runner, packaging).
- **P3 — Nilakhya** — data, UI, compliance, evidence, and the deliverables (README/video/slides).

> Swarm principle: everyone can do everything. These are **accountability** boundaries — the named owner
> guarantees the piece lands, keeps its docs current, and can defend it in the AI discussion. Anyone finishing
> early pulls the next unblocked task from another lane (overflow rules at the bottom).

---

## 0. Frozen on Day 1 (the seams that let us parallelize)
Nobody waits on anybody if these three contracts are frozen first. **Owner: P1, with P2 review, Day 1.**
1. **VoI Receipt JSON schema** (`PLAN.md` §7.3) — the object every layer reads/writes.
2. **`Detector` base interface** — `name, axis, tier, cost_usd, run(ctx) -> Signal{score, raw, latency_ms}`.
   Every detector (P1) and the harness (P2) code against this.
3. **`CascadeResult` / policy input contract** — what the cascade hands the policy engine and the recorder.

Once these exist as stub files with types + docstrings (even returning fakes), all three lanes build in
parallel against them.

---

## 1. P1 — Dhruv · VoI Engine & Integration (the brain)

**Mission:** own the parts that make ControlPlane *novel and correct* — the economic decision rule, the
detectors, and the proof engines — and hold the end-to-end integration together.

**Owned modules:** `cascade/` (engine, voi, thermostat, detectors/*), `pnl/`, `replay/`, `recorder/receipt.py`,
overall integration + the demo storyline.

**Ordered backlog:**
1. *(Day 1)* Freeze the 3 contracts (§0). Stand up `cascade/engine.py` as a no-op that emits a valid receipt.
2. *(Day 2–3)* Real detectors, T0 + T1 per axis, against the `Detector` interface:
   - Performance: sampled self-consistency + semantic clustering; groundedness via HHEM-2.1-Open / MiniCheck.
   - Cost: model-overkill heuristic, semantic cache (embed→cosine), router decision (RouteLLM-style/heuristic).
   - Responsibility: GLiNER PII (+Presidio fallback); lightweight safety/injection classifier.
3. *(Day 4–5)* **The core:** `voi.py` — expected-loss math, per-axis **calibration** (isotonic/Platt),
   **stopping rule** (`Δloss vs cost+λ·latency`). Unit-tested. This is the contribution — get it right.
4. *(Day 4–5)* `pnl/` — pricing table + Oversight P&L ledger (cost saved / safety spend / net) writing into receipts.
5. *(Day 4–5)* `replay/` — re-run a recorded workload under an alternate policy/budget → counterfactual $ + failures.
6. *(Day 6)* `thermostat.py` — feedback controller over recent risk + remaining budget; demo via a risk burst.
7. *(Day 6, stretch → agentic)* trajectory-audit detector + mid-stream abort hook (with P2's streaming plumbing).
8. *(Day 7+)* Calibration/reliability diagrams, ablation runs, tighten the demo narrative, integration bug-fixing.

**Acceptance:** a request produces a correct, chained receipt; the stopping rule provably cuts cost vs
verify-all at ≥ equal caught-failure rate on the eval set; ECE reported; replay reproduces the live P&L.

**Must be able to explain live (AI discussion):** why VoI beats fixed thresholds; how calibration makes
`P(fail)` honest; the exact stopping condition and how `Cost(fail)`/λ tune the over/under-flag tradeoff; why
semantic entropy / self-consistency detects hallucination without ground truth; how the P&L is computed and
why it can go net-negative.

---

## 2. P2 — Yugal · Platform & Systems

**Mission:** make ControlPlane a real, runnable, reproducible system — the gateway, the durable log, the
governance layer, the concurrency that protects latency, and the benchmark that produces our numbers. Your
Spring/system-design instincts, expressed in Python.

**Owned modules:** `proxy/`, `recorder/store.py`, `policy/`, `eval/run.py`, `eval/metrics.py`, packaging/Docker.

**Ordered backlog:**
1. *(Day 1)* FastAPI **OpenAI-compatible proxy** — `/v1/chat/completions` passthrough via `litellm`; the
   one-line base-URL swap works end-to-end through a no-op cascade. Co-own the §0 contracts with P1.
2. *(Day 2–3)* **Flight recorder** — SQLite, append-only, **SHA-256 hash chain**, plus a query API the UI reads.
3. *(Day 2–3)* **Policy engine** — YAML schema (per use-case × geography × risk appetite), validation,
   **hot-reload**; carries `Cost(fail)`, λ, and per-axis tier ceilings that feed P1's stopping rule.
4. *(Day 3)* **Concurrency model** — run detectors in parallel with `asyncio`, per-tier timeouts, latency-budget
   enforcement. This *is* the brief's "checks run in parallel to protect latency" — make it measurable.
5. *(Day 4)* **Streaming + mid-stream abort** plumbing in the proxy (hook P1's abort predicate).
6. *(Day 3–5)* **Eval harness runner** (`eval/run.py`) + **baselines** (verify-none, verify-all) +
   `eval/metrics.py` (P/R/F1/FPR/FNR, added-latency p50/p95, %-cleared-at-T0, $ saved, calibration ECE).
7. *(Day 8)* **Packaging** — `docker-compose up` brings up proxy + UI + a mock model; `make demo` / `make eval`;
   `.env.example`; write the "execution instructions" half of the README so a stranger runs it in one command.

**Acceptance:** clean clone → `docker-compose up` → working proxy; streaming + abort demoed; policy hot-reload
works; `make eval` regenerates the full metrics table with baselines.

**Must be able to explain live:** where the checker sits (inline middleware/pre-response gate) and the trade
vs post-hoc audit; how parallel async detection keeps added latency low; the hash-chain tamper-evidence claim
(and its honest limits); how a policy profile changes behavior per use-case/geo/risk without code changes.

---

## 3. P3 — Nilakhya · Data, UI, Compliance & Deliverables

**Mission:** give us the workload we measure on, the UI that sells the story, the auditor-ready compliance
artifact, and the submission package — and protect our credibility by verifying every claim.

**Owned modules:** `EVIDENCE.md`, `eval/inject.py` + `data/`, `ui/`, `compliance/`, README/video/slides.

**Ordered backlog:**
1. *(Day 1–2, P0 GATE)* **Evidence verification.** Web-verify the three R1 "2026 incidents" + the technique
   claims (MiniCheck 400×, RouteLLM 95%, EU AI Act Art. 50 date, etc.). Produce `EVIDENCE.md`: one primary
   link per claim; flag anything unverifiable for replacement. **No slide/README ships a claim not in this file.**
2. *(Day 2–3)* **Failure-injection dataset** — fetch + **license-check** public sets (HaluEval/RAGTruth for
   hallucination; a PII set; a safety/bias subset), write labeled injectors in `eval/inject.py`; document each
   dataset's license in `EVIDENCE.md`. Large files gitignored; scripts fetch them.
3. *(Day 4–6)* **Control-Tower UI** (`ui/`) consuming P2's recorder API + P1's live feed: live fleet, **Oversight
   P&L**, incidents, **drill-into-a-receipt**, **confidently-wrong quadrant**, thermostat gauge. Next.js hero;
   **Streamlit fallback** if React is slow (Day-4 go/no-go with P1).
4. *(Day 6)* **Compliance evidence-pack** generator (`compliance/`) — mapping table + template turning real
   receipts into a markdown/PDF pack keyed to EU AI Act Art. 50 / ISO 42001 / NIST AI RMF.
5. *(Day 7–9)* **Deliverables** — README polish (approach + key features half; P2 owns the run half), **2–3 min
   demo video** (screen-record the live `make demo`), finale slides, the two dry-run recordings.

**Acceptance:** `EVIDENCE.md` has zero unverifiable claims; UI renders live feed + P&L + drill-in from real
receipts; injectors produce labeled data the harness scores; compliance pack generates from real receipts;
video is cut and under time.

**Must be able to explain live:** what each detection axis catches and its FP/FN behavior; how the P&L and
quadrant are computed; how the compliance pack maps to each regulation; why our datasets/injections are a fair
test and where they're limited.

---

## 4. Shared / paired work
- **Integration** (P1 lead, all): daily merge to a runnable `main`; P1 reviews every PR.
- **Eval numbers** (P2 runner + P1 metrics/calibration + P3 data): the results table is a three-person artifact.
- **README** (P3 approach/features + P2 execution): one doc, two owners.
- **Demo dry-runs** (all, Day 7 & Day 9): record, watch back, cut anything that doesn't land in 3 minutes.

## 5. Dependencies (watch these handoffs)
- Everyone → **§0 contracts** (P1, Day 1). Blocker if late; do it first.
- UI (P3) → recorder query API (P2) + receipt shape (P1). P2 ships a stub-with-fake-rows Day 2 so P3 isn't blocked.
- Eval metrics (P2) → labeled injectors (P3) + detector outputs (P1). P3 ships a tiny labeled sample Day 2.
- Replay/P&L (P1) → recorder writes (P2). P2's recorder is on the critical path — prioritize it Day 2.
- Compliance pack (P3) → receipts exist (P1/P2). Fine by Day 6.

## 6. Overflow rules (when you finish early / get blocked)
1. Help unblock the **critical path** first (recorder → cascade → eval → UI, in that order of leverage).
2. Then take the next **P1-tier** differentiator from `PLAN.md` §5 (replay, thermostat, compliance, mid-stream abort).
3. Then write **tests and docs** for someone else's module (forces the explain-back, raises quality).
4. Never start a **P2/COULD** item while any **P0** item is unfinished anywhere on the team.

## 7. Cadence
- **Daily 15-min async standup**: yesterday / today / blockers, in the shared channel; task state in `STATUS.md`
  or a GitHub Projects board.
- **Small PRs** (< ~400 lines), P1 reviews & merges, `main` always runs.
- **Feature freeze Day 7 (Aug 28)** — after that only bug-fixes, polish, docs, and the video.
