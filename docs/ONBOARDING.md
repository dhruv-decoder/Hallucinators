# Team Onboarding — What We Built and Where to Start

Read this first. It explains, in plain language, what ControlPlane is and what already works, then gives
Yugal and Nilakhya an ordered checklist to start from. Deep detail is in [PLAN.md](PLAN.md),
[ARCHITECTURE.md](ARCHITECTURE.md), and [WORKPLAN.md](WORKPLAN.md).

---

## Part 1 — What ControlPlane is, in plain words

Think of an **air-traffic control tower for AI answers**. Every answer an AI gives passes through the tower
before it reaches the user. The tower asks three questions about each answer:

1. **Performance** — is it wrong, or confidently wrong?
2. **Cost** — did we use an expensive model when a cheap one would do?
3. **Responsibility** — is it biased, unsafe, or leaking someone's private data?

The clever part — and the thing nobody else has built — is **how much checking each answer gets**. Checking
costs money and time. So instead of running every expensive check on every answer (slow and costly) or
skipping checks (risky), ControlPlane treats each check as a **purchase decision**: it runs a check only if
that check could actually change what we do with the answer. Cheap checks run first; expensive checks run
only when they're worth it.

And here's the money line: the **cost** checks *save* money (by sending easy questions to a cheaper model,
or reusing a cached answer), and those savings **pay for** the safety checks. So the whole safety layer can
end up costing *less than nothing* — "safer AND cheaper." We prove this with a live profit-and-loss ledger.

### The one formula (this is the heart)
For an answer, let `p` = our estimated chance it's a failure, `C` = how bad it is if that failure reaches a
user, `m` = the cost of doing something about it (block/escalate/edit). We run the next check only if:

> **value of the check** `= how much it reduces expected loss` **is greater than** `what the check costs (money + time)`

That single rule is what makes us different from every guardrail/observability tool on the market.

### What each part of the code does (one line each)
- `controlplane/core/types.py` — the shared "vocabulary": what a Signal, a RequestContext, a Receipt look like.
- `controlplane/cascade/voi.py` — the formula above: the value-of-information decision.
- `controlplane/cascade/calibration.py` — makes our "chance of failure" numbers honest (learned from data).
- `controlplane/cascade/detectors/` — the individual checkers (PII, groundedness, overconfidence, cost).
- `controlplane/cascade/engine.py` — runs the checkers cheapest-first and applies the decision rule.
- `controlplane/pnl/` — the profit-and-loss ledger (money saved vs money spent on safety).
- `controlplane/recorder/` — writes a tamper-evident "receipt" for every decision (the audit trail).
- `controlplane/demo/run_demo.py` — a runnable demo that sends 5 example questions through the whole thing.

### See it work (2 minutes, no API keys needed)
```bash
make install     # one-time: makes a .venv and installs everything
make test        # runs the 20 unit tests (all pass)
make demo        # sends 5 sample questions through the tower and prints the decisions + P&L
```

The demo shows: a clean answer passed (and routed to a cheaper model to save money), a confident-but-wrong
answer escalated to a human, a private-data leak blocked, a repeated question served from cache, and an
uncertain answer where the tower decided a deeper check was worth running. Bottom line printed at the end:
**net cost was negative — the safety checks paid for themselves.**

---

## Part 2 — Yugal (P2): the platform. Start here, in order.

You own the parts that turn the engine into a real, runnable, reproducible **system**: the gateway that
sits in front of any model, the durable audit store, the governance policy layer, and the benchmark. This
plays directly to your system-design strengths, in Python.

**0. Get oriented (½ day).** Clone the repo. Run `make install`, `make test`, `make demo`. Read
   [ARCHITECTURE.md](ARCHITECTURE.md) and skim `controlplane/core/types.py` — those types are the contract
   you build against. You do not need to understand the VoI math deeply yet; you need the shapes of
   `RequestContext`, `VoIReceipt`, and `CascadeEngine.run()`.

**1. The OpenAI-compatible proxy — your first real build.** Create `controlplane/proxy/app.py`, a FastAPI
   app exposing `POST /v1/chat/completions` (the standard OpenAI shape). For each incoming request:
   call the upstream model via `litellm`, build a `RequestContext` (prompt + the model's reply, plus any
   retrieved context the caller passed), run `CascadeEngine.run(ctx)`, book the P&L, save the receipt, then
   apply the action (pass = return as-is; annotate = add a caveat; block = withhold; escalate = flag). Return
   an OpenAI-shaped response. Install with `pip install -e ".[serve]"`.
   - **Done when:** `curl` to your proxy returns an answer, and a receipt is recorded for it. This is the
     "one-line base-URL swap" the pitch promises — make it real.

**2. Streaming + a place to abort.** Support `stream=true` (token-by-token). Add a hook in the streaming
   loop where an "abort predicate" can stop a bad/looping generation early. Leave the predicate as an
   interface for now (P1 fills it in). Structure matters here more than the predicate.
   - **Done when:** streaming works, and there's a clean seam where mid-stream abort will plug in.

**3. SQLite flight recorder + query API.** Create `controlplane/recorder/sqlite_store.py` with the *same*
   interface as the existing `JsonlRecorder` (`record`, `verify_chain`) but backed by SQLite so receipts
   survive restarts. Then add a **query API** the UI will call: list receipts (filter by use_case / action /
   time), get one by id, and aggregate the running P&L. Keep the SHA-256 hash chain.
   - **Done when:** receipts persist across restarts, `verify_chain()` still passes, and `get_receipts(...)`
     returns filtered rows. **This unblocks Nilakhya's UI**, so it's high priority.

**4. Policy engine.** Create `controlplane/policy/` — a loader that reads YAML profiles (one per
   use-case × geography × risk appetite) into the existing `PolicyProfile`, with validation and **hot-reload**
   (re-read on file change or via an endpoint). The proxy picks a profile based on the request's use_case.
   - **Done when:** editing a YAML value (say `block_threshold`) changes behavior with no restart.

**5. Parallel detectors (protect latency).** Right now detectors run one after another. Wrap the
   within-a-tier detector runs in `asyncio.gather` with per-tier timeouts, so checks run in parallel. Measure
   the added latency (p50/p95) and how much traffic clears at Tier 0.
   - **Done when:** you can report "median added latency = X ms, 95th percentile = Y ms."

**6. Eval harness runner + metrics.** Create `controlplane/eval/run.py` and `metrics.py`: take a labelled
   dataset (Nilakhya provides), run each item through the engine, and compute precision / recall / F1 /
   false-positive-rate / false-negative-rate per axis, plus $ saved vs two baselines (check-everything and
   check-nothing). This is our credibility backbone — coordinate with P1 (calibration) and Nilakhya (data).
   - **Done when:** `make eval` prints a metrics table with baselines.

**7. Docker + one-command run.** `docker-compose.yml` brings up proxy + UI + a mock model; `make demo` and
   `make eval` work on a fresh clone. Write the "how to run it" half of the README.
   - **Done when:** a stranger clones the repo and runs everything with one command.

*Order logic:* 1→3 first (they unblock live demos and Nilakhya's UI), then 4→5 (governance + latency), then
6→7 (proof + packaging). Items 1, 3 are the critical path.

---

## Part 3 — Nilakhya (P3): data, UI, evidence, deliverables. Start here, in order.

You own the things that make the work *provable* and *presentable*: the test data we measure on, the
dashboard that sells the story, the compliance artifact, and the final video/slides — plus protecting our
credibility.

**0. Get oriented (½ day).** Clone the repo. Run `make install`, `make test`, `make demo`. Read
   [PLAN.md](PLAN.md) (the story) and [JUDGE.md](JUDGE.md) (how we're scored). Watch the demo output closely
   — that's the story your UI and video will tell.

**1. EVIDENCE.md — lock our credibility (do this first).** Create `docs/EVIDENCE.md`. The three 2026
   incidents from our Round-1 slide are confirmed; now **record the exact primary source (a real link) for
   each one**, so we can show it under questioning. Do the same for the technique claims we cite (MiniCheck
   "400x cheaper", RouteLLM "95% of GPT-4", the EU AI Act Article 50 date) and note the licence of any
   dataset we use. **Also find real, current model prices** (OpenAI / Anthropic) and give them to P1 so we can
   replace the clearly-labelled placeholder prices in `controlplane/pnl/pricing.py`.
   - **Done when:** every number we plan to show on a slide has a link next to it in EVIDENCE.md, and we have
     real prices for the P&L.

**2. Failure-injection dataset.** Create `controlplane/eval/inject.py` and a `data/` folder. Assemble a
   small **labelled** test set: pull public data (e.g. HaluEval or RAGTruth for hallucinations, a PII sample,
   a safety/bias sample), and write simple scripts that produce labelled `RequestContext` records — each
   tagged with which axis fails and whether it's truly a failure. Start small and honest; licence-check each
   source and record it in EVIDENCE.md. Large files stay out of git (scripts fetch them).
   - **Done when:** `inject.py` produces a set of labelled requests the eval harness can score. **This unblocks
     Yugal's metrics (his item 6).**

**3. Control-Tower UI.** Build the dashboard in `ui/`, reading from Yugal's recorder query API (his item 3).
   Panels: a **live feed** of decisions, the **Oversight P&L** (saved / spent / net), an **incidents** list,
   **click-into-a-receipt** to show the VoI trace (why we stopped where we did), and the **confidently-wrong
   quadrant** (confidence vs correctness). Start with **Streamlit** to get something on screen fast; we can
   upgrade the hero screen to Next.js later.
   - **Done when:** the UI shows real receipts and a live P&L from the recorder.

**4. Compliance evidence-pack.** Create `controlplane/compliance/` — a generator that turns receipts into an
   auditor-ready pack mapping each decision to EU AI Act Article 50 / ISO 42001 / NIST AI RMF controls
   (markdown, then PDF). Accenture cares a lot about this.
   - **Done when:** one command produces a compliance pack from real receipts.

**5. Deliverables.** README polish (the "what it does / key features" half), the 2–3 minute demo video
   (screen-record `make demo` and the UI, narrate the story), and the slides.
   - **Done when:** a stranger understands the whole thing from the README + video in five minutes.

*Order logic:* 1 first (protects us and unblocks pricing), 2 next (unblocks Yugal's metrics), then 3 (needs
Yugal's item 3), then 4→5.

---

## Part 4 — How the three of us stay in sync
- Keep `main` runnable. Small pull requests. P1 (Dhruv) reviews and merges.
- A 15-minute async standup daily: yesterday / today / blockers.
- The contracts in `core/types.py` are frozen — build against them, don't change them without telling everyone.
- Rule that beats all others: **we only ship what all three of us can explain.** If you can't explain a piece
  of AI-written code, rewrite it until you can. See [AI_CODING_GUIDELINES.md](AI_CODING_GUIDELINES.md).
