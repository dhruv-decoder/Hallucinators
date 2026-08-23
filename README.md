# ControlPlane

Real-time oversight for enterprise AI, framed as a **value-of-information (VoI) decision under a latency
budget**: for every model response, decide *how much verification that response is worth*, buy the cheapest
signal that could change the decision first, and let cost-axis savings help pay for the safety checks.

One layer, three coupled risks, one verdict:

- **Performance** — is the answer wrong, or confidently wrong?
- **Cost** — is this the cheapest path to this quality?
- **Responsibility** — is it biased, unsafe, or leaking data?

> Status: **working prototype.** The decision engine (the VoI cascade, calibration, expected-loss stopping
> rule, P&L ledger, hash-chained receipts, and the What-If/Replay simulator), **the OpenAI-compatible proxy
> ("The Tower") with inline auto-repair / PII-redaction / mid-stream abort, and the live Control-Tower
> dashboard** all run today and are unit-tested (51 tests). Point any OpenAI client at it with a one-line
> `base_url` swap. The richer model-backed detectors (HHEM/MiniCheck groundedness, GLiNER, safety models)
> and labelled public-data evals are the next lift. What is implemented vs. planned is stated honestly below
> and in [docs/PLAN.md](docs/PLAN.md). New here? Read [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) first — it
> explains every component and the end-to-end user flow with diagrams.

## Why this is different

Existing tools *watch*, *guard*, *observe*, or *cut cost* — separately, after the fact, with four different
verdicts. ControlPlane runs oversight as one economic decision across three axes: it only spends on a check
when the check's expected reduction in loss beats its own cost and latency. See
[docs/PLAN.md](docs/PLAN.md) §3–§4 for the full positioning and competitive comparison.

## What runs today

- **The Tower — OpenAI-compatible proxy** (`controlplane/proxy/`) — a real `/v1/chat/completions` gateway
  (streaming + non-streaming). Point any OpenAI client's `base_url` at it and every response is overseen
  inline: **auto-repaired** from retrieved context, **PII-redacted / blocked**, or **escalated** to a human,
  with a **mid-stream abort** that stops a leak before the tokens leave. Runs fully offline via a simulated
  failure-injecting upstream (no keys, no downloads); routes to real models via `litellm` when a key is set.
- **Control-Tower dashboard** (`controlplane/proxy/static/`) — a live, single-file UI served by the proxy:
  the Oversight P&L going net-negative, the confidently-wrong quadrant, the adaptive thermostat, and a
  click-into-any-receipt drawer with the full value-of-information trace. `make serve`, then open the page.
- **Agentic trajectory oversight** (`controlplane/agent/`) — the VoI cascade extended to a whole tool-calling
  agent. It runs the three-axis check on every step *plus* trajectory-level signals (compounding risk, loops,
  tool-call waste) and **aborts mid-run on the unrecoverable failure**, escalating to a human. The finale demo
  (`make agent`) shows an agent compounding a hallucination and looping; the auditor stops it and books the
  avoided steps as savings (the agent "waste-killer").
- **Layered safety detectors** (`controlplane/cascade/detectors/safety.py`) — prompt-injection/jailbreak
  (ingress) and unsafe-content (egress) checks on the responsibility axis, matching the 2026 layered-guardrail
  consensus (upgrade paths: PromptGuard-2, Llama Guard 4 / ShieldGemma-2).
- **Compliance evidence pack** (`controlplane/compliance/`) — maps the hash-chained receipts to concrete
  **EU AI Act** (Arts. 12/13/14/15/26/50), **ISO/IEC 42001**, and **NIST AI RMF** controls, exported as JSON
  or a downloadable Markdown pack. Governance stays policy-as-config; evidence is generated on demand.
- **VoI decision engine** (`controlplane/cascade/voi.py`) — expected loss `= P(failure) x Cost(failure)`, the
  value-of-information of the next check, and the stopping rule that decides whether to climb a tier.
- **Probability calibration** (`controlplane/cascade/calibration.py`) — Platt and isotonic (PAV)
  calibration + Expected Calibration Error, so `P(failure)` is honest rather than a raw detector score.
- **Tiered cascade** (`controlplane/cascade/engine.py`) — orchestrates detectors T0 -> T1 -> T2, climbing
  only when the stopping rule says a check is worth it.
- **T0 detectors** (`controlplane/cascade/detectors/`) — real, lightweight heuristics for PII, groundedness,
  overconfidence, and model-overkill, each with a documented upgrade path to a heavier model.
- **Oversight P&L** (`controlplane/pnl/`) — cost saved vs. safety spend vs. net, per request.
- **Flight recorder** (`controlplane/recorder/`) — every decision becomes a hash-chained, tamper-evident
  receipt (reference JSONL store; SQLite upgrade in progress).
- **What-If / Replay simulator** (`controlplane/replay/`) — re-runs a workload under different oversight
  policies (and oversight-off) to show the residual-risk vs. cost trade-off and prove the P&L is self-funding.
- **Adaptive Oversight Thermostat** (`controlplane/cascade/thermostat.py`) — a feedback controller that
  raises verification thoroughness when recent risk spikes and relaxes it when traffic is calm.
- **Optional model-backed PII** (`controlplane/cascade/detectors/responsibility_ml.py`) — a real Presidio +
  spaCy NER detector that catches free-text names/locations the regex misses (`[ml]` extra; see below).
- **Feedback loop** (`controlplane/feedback/`) — human overrides on flagged decisions refit detector
  calibration, so detection gets more honest over time (`python -m controlplane.demo.run_feedback`).
- **Evaluation harness** (`controlplane/eval/`) — `make eval` reports per-axis precision/recall/F1/FPR/FNR
  against no-oversight and flag-everything baselines, plus cost and calibration, all reproducibly.

## Run it

```bash
make install      # creates .venv and installs the core engine + dev tools
make test         # unit tests for the VoI math, calibration, P&L, replay, and the proxy
make demo         # runs sample requests through the cascade and prints receipts + a P&L summary
make whatif       # re-runs a workload under strict/balanced/lenient/off to show the risk-vs-cost trade-off
```

**See the whole thing live (the Tower + Control-Tower dashboard):**

```bash
make install-serve   # adds the proxy deps (FastAPI, uvicorn, httpx)
make serve           # starts The Tower on http://127.0.0.1:8000  → open it in a browser
make traffic         # (in a second terminal) fires the demo workload at it via a one-line base_url swap
```

Then click **“Send demo traffic”** on the dashboard and watch the Oversight P&L go net-negative in real
time. Everything needs no API keys or model downloads — the engine, T0 heuristics, and the simulated
failure-injecting upstream all run locally. Set `OPENAI_API_KEY` (and `pip install -e ".[providers]"`) to
route to a real model instead.

### Run on Windows (VS Code)

`make` is not installed on Windows by default, so run the commands directly. Everything else is
cross-platform.

**One-time setup**
1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/). On the first
   installer screen, tick **"Add python.exe to PATH"**.
2. Install **Git** from [git-scm.com](https://git-scm.com/download/win).
3. Install **VS Code** and its Microsoft **Python** extension.

**Get the code and run it**
1. Open VS Code, then open a terminal (`Ctrl + ~`) and clone the repo:
   ```powershell
   git clone https://github.com/dhruv-decoder/Hallucinators.git
   cd Hallucinators
   ```
   (The repo is private — sign in / authorise GitHub when prompted. You must be added as a collaborator.)
2. Open the folder in VS Code: **File > Open Folder** → select `Hallucinators`.
3. Create and activate a virtual environment in the **PowerShell** terminal:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks the activation script with an execution-policy error, run this once and then
   activate again:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```
   (Alternatively use the **Command Prompt** terminal and run `.venv\Scripts\activate.bat`.)
4. Install the project:
   ```powershell
   python -m pip install --upgrade pip
   pip install -e ".[dev]"
   ```
5. Run the tests and demos:
   ```powershell
   pytest
   python -m controlplane.demo.run_demo
   python -m controlplane.demo.run_whatif
   ```

**VS Code tips**
- After creating `.venv`, press `Ctrl + Shift + P` → **Python: Select Interpreter** → choose the one in
  `.venv`. New terminals then activate it automatically.
- If `python` is not found, try `py -3` instead (e.g. `py -3 -m venv .venv`).

## Repository layout

```
controlplane/         # the Python package
  core/               # shared contracts: types, Detector interface, receipt schema
  cascade/            # VoI engine, calibration, tier orchestration, detectors
  pnl/                # pricing table + Oversight P&L ledger
  recorder/           # receipt builder + hash-chained store
  replay/             # What-If / Replay simulator (the proof engine)
  feedback/           # override -> recalibrate learning loop
  eval/               # labelled failure-injection harness + metrics + baselines
  agent/              # agentic trajectory oversight (per-step cascade + compounding/loop/waste checks)
  compliance/         # EU AI Act / ISO 42001 / NIST AI RMF evidence-pack generator
  proxy/              # The Tower: OpenAI-compatible gateway + oversight service + dashboard (static/)
  demo/               # end-to-end runnable demos
tests/                # unit tests
docs/                 # WALKTHROUGH (start here), PLAN, ARCHITECTURE, JUDGE, DECISIONS, WORKPLAN
  reference/          # competition briefs and the Round-1 solution
```

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — the master plan (scope, architecture, roadmap).
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the engine works, including the VoI derivation.
- [docs/DECISIONS.md](docs/DECISIONS.md) — architecture decision records.
- [docs/JUDGE.md](docs/JUDGE.md) — the R2 brief decoded into a rubric we self-score against.

## License

MIT — see [LICENSE](LICENSE).
