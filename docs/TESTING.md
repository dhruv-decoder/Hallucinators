# How to test the flows (5 minutes)

Everything runs on your Mac; no cloud needed. Two ways to run — pick one.

## Run it

**Single service (what deploys):**
```bash
make install-serve        # backend deps (once)
make web-build            # build the React UI (needs Node; once, or after UI changes)
make serve                # http://127.0.0.1:8000
```
Open **http://127.0.0.1:8000** → you land on the marketing page → click **Launch the live Control Tower**.

**Frontend hot-reload (while editing the UI):**
```bash
make serve                # terminal 1 (backend :8000)
make web-dev              # terminal 2 (UI :3000, /api proxied)  → http://localhost:3000
```

> Enable the real models first (optional, uses your free Groq key + M4 GPU):
> `pip install -e ".[ml]"` then run `make serve` **without** `CONTROLPLANE_MODELS=off`. `.env` (with `GROQ_API_KEY`)
> is auto-loaded. Check `GET /healthz` — you should see `groundedness: hhem-2.1-open`, `judge: groq`.

## Click-through checklist (the demo flows)

1. **Landing** — hero, live P&L ticker, "three coupled risks", the measured proof strip, how-it-works, one-line swap. Toggle **light/dark** (top-right sun/moon). → *Feels like a product; theme works.*
2. **Launch dashboard** → **Overview**. Click **▶ Send demo traffic** (top-right). → *KPIs fill, the P&L sparkline dips below zero (self-funding), recent decisions stream in.*
3. **Live feed** → click any row. → *Receipt drawer opens with per-axis bars, the value-of-information trace (which checks ran/were skipped and why), cost opportunities, and the tamper-evident hash.* Filter by action (block/escalate/…).
4. **Confidently-wrong** → *dots plotted by correctness × confidence; the shaded top-left is the danger zone.*
5. **Latency & scale** → **Run benchmark**. → *A real progress bar with ETA, then p50/p95/p99 added latency, throughput, and an at-scale $ extrapolation.*
6. **What-If replay** → **Run replay**. → *oversight-off vs strict/balanced/lenient; every ControlPlane row is net-negative.*
7. **Agent oversight** → **Run agent trajectory**. → *step-by-step verdicts; the agent hallucinates, loops, and is **aborted** mid-run and escalated — wrong answer never ships, wasted steps saved.*
8. **Compliance** → **Generate evidence pack** (+ download Markdown). → *receipts mapped to EU AI Act / ISO 42001 / NIST controls.*
9. **Detectors & models** → *shows whether HHEM / Groq judge are live (vs heuristic fallback).*
10. **Policy switch** (top-right dropdown) → *support_bot ↔ internal_copilot changes risk appetite live.*

## The "one-line swap" (prove it's a real proxy)

With the server running, in another terminal:
```bash
make traffic              # points a plain OpenAI-style client at http://127.0.0.1:8000/v1
```
Or from Python — this is all an integrator changes:
```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="anything")
r = client.chat.completions.create(model="gpt-4o",
    messages=[{"role":"user","content":"What is the refund window?"}])
print(r.choices[0].message.content)        # auto-repaired, grounded answer
print(r.controlplane)                       # action, per-axis p_fail, net $, receipt id
```

## Prove the numbers (honest evals)

```bash
make test                                   # 73 unit tests (VoI, calibration, proxy, agents, compliance, models)
make eval                                   # synthetic labelled set: P/R/F1/FPR/FNR vs baselines (reproducible)
pip install -e ".[eval]" && make eval-real            # REAL HaluEval: lexical groundedness F1 ~0.30
make eval-real ARGS="--models"                        # same data + HHEM on the tail: F1 ~0.76 (needs [ml])
```

## Automated checks
- Backend: `make test` (pytest) + `make lint` (ruff).
- Frontend: `cd web && npm run typecheck && npm run build`.
