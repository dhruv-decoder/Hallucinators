# The 3-minute demo — script, setup, and what to show

## Where to demo from (recommendation)
- **Record the video from LOCAL** (`make serve` on your Mac) with models ON (Groq judge + M4-GPU HHEM). You
  get full control, no cloud cold-start, and the real model tier is live. This is your primary artefact.
- **Also ship the deployed Render link** in the README/submission so judges can click and try it themselves
  (it runs offline/simulated, no keys — safe and always-up).
- **For the live finale**, present from LOCAL (reliable) and keep the Render link as a backup on a second tab.

### One-time setup for the "models-on" demo
```bash
pip install -e ".[ml]"                 # HHEM groundedness (uses your M4 GPU)
# .env already has GROQ_API_KEY (the judge is gpt-oss-120b, free)
make web-build && make serve           # http://localhost:8000
```
Open the page; keep a terminal ready for `make traffic` if you want the one-line-swap beat.

---

## The script (≈3:00) — one story, one breath per beat

**0:00–0:20 · The problem + the moat (say it in one breath).**
> "Enterprises run AI everywhere, and today oversight is four separate tools — hallucination evals, guardrails,
> observability, cost — all after the fact, four verdicts. ControlPlane gives **one verdict across three
> coupled risks**, decides **how much verification each response is worth**, and — the part nobody else does —
> **it pays for itself and gives a statistical guarantee.** Safer *and* cheaper, with a certificate."

**0:20–0:45 · It's a real product, not a wrapper.** Land on the **Use-case setup** wizard. Pick *support bot ·
real-time · low risk · regulated · EU*. Hit **Generate** → show the tuned knobs, the projection (cleared@T0,
p95 latency, monthly net $), and the **plain-English reason for every knob**. → *"You describe your use case;
the policy is generated and applied — different use cases, different budgets, exactly what the brief asks."*

**0:45–2:15 · Watch it run live.** Click **Send demo traffic**.
- **Overview:** the **Oversight P&L dips below zero** — savings pay for the safety checks. (Point at it.)
- **Live feed → click one receipt:** the **value-of-information trace** — which checks ran, which were
  skipped, and why. → *"Every decision is auditable."*
- Call out the **two-axis case** ("account manager … personal cell") → hallucination **and** privacy, one
  verdict, escalated to a human. And the **PII block** and **bias** case.
- **Agent oversight → Run:** the agent hallucinates a "365-day refund", **loops to confirm its own
  invention**, and gets **aborted mid-run** and escalated. → *"Compounding risk, caught."*
- **Latency & scale → Run benchmark:** progress bar → **p95 ~0.16 ms added, ~7,100 req/s.** → *"It doesn't
  slow the model down."*

**2:15–2:40 · The two differentiators, proven.**
- **Conformal guarantee:** *"We don't just score risk — we **control** it: escaped-failure rate ≤ α with a
  finite-sample certificate."* (Show the eval line or the panel.)
- **Measured on real data:** *"On HaluEval, the cheap check gets F1 0.30; the cascade climbing to HHEM on the
  uncertain tail gets **0.76** — reproducible with `make eval-real`."*

**2:40–3:00 · Close.** **Compliance → Generate pack** (EU AI Act / ISO 42001 / NIST). → *"Auditor-ready
evidence, humans in the lead on the uncertain tail, and a P&L that's net-negative. That's ControlPlane."*

---

## The one-liner for the "how is this different from X?" question
> "Everyone else adds an oversight tax and watches one axis after the fact. We run oversight as a **budget**:
> the cost axis funds the safety axis, we buy a check only when it could change the decision, and we hand you a
> **certificate** on the escaped-failure rate. Guardrails/Arize/Galileo/TrueFoundry each do a slice; we unify
> them into one economic verdict with a guarantee."

## Backup answers (rehearse)
- *"Is the traffic real?"* → The **engine is real and computes every number live**; the demo **upstream is a
  simulated failure-injector** so it runs offline. Point it at a real model (Groq/OpenAI) and it's identical.
- *"Judges are unreliable."* → Yes (RAND 2026: >50% error on bias) — that's why the judge is **one VoI-gated,
  calibrated signal** combined via noisy-OR, not an oracle, and why the conformal guarantee matters.
- *"Detectors are heuristics."* → The model tier (HHEM, gpt-oss judge/safeguard) is real and measured; the
  *decision framework* is the contribution.
