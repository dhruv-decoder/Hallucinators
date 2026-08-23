# Deploying The Tower

The whole product is **one FastAPI service** (proxy + dashboard). You do not need AWS, Kubernetes, or a GPU
for the demo — a single free web service is enough. GPU/microservices are only for scale (see the bottom).

## Local (laptop) — the default
```bash
make install-serve && make serve      # http://127.0.0.1:8000
```
Runs fully offline (simulated failure-injecting upstream). To use real models: `pip install -e ".[providers]"`
and set `OPENAI_API_KEY` (or run Ollama for the judge). `GET /healthz` shows what's active.

## Render (free tier) — one-click demo
`render.yaml` is committed, so:
1. Push the repo to GitHub (already done).
2. On Render → **New → Blueprint** → point at the repo. It reads `render.yaml` and deploys a single web
   service. Render injects `$PORT`; the app reads it automatically.
3. Open the URL — the dashboard is at `/`, the OpenAI API at `/v1`.

It deploys with `CONTROLPLANE_FORCE_SIM=1` (offline, no keys). To route to a real model, add `OPENAI_API_KEY`
in the Render dashboard and change the build to `pip install -e ".[serve,providers]"`.

## Docker — anywhere
```bash
docker build -t controlplane .
docker run -p 8000:8000 controlplane          # http://localhost:8000
```

## Vercel
Vercel hosts frontends, not a long-running Python server. Since the dashboard is served *by* the FastAPI app,
Render/Docker is the right home for the whole thing. If you later split a separate Next.js frontend, host that
on Vercel and point it at the Render backend's `/v1/oversight/*` API (it is CORS-simple and stateless to read).

## When you actually need the A100 / AWS microservices
Only for **scale**, not the demo:
- serving a **larger local judge** (or HHEM/MiniCheck) at high QPS,
- running the **full benchmark sweep** (tens of thousands of examples through a 7B model) fast,
- **multi-tenant** isolation, autoscaling, and a real datastore for the flight recorder (SQLite → Postgres).
The code is written so these are swaps behind existing seams (upstream, recorder, detector factory), not a
rewrite — hand them to whoever owns infra.
