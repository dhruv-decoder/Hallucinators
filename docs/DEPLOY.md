# Deploying The Tower

The whole product is **one FastAPI service** (proxy + dashboard). You do not need AWS, Kubernetes, or a GPU
for the demo — a single free web service is enough. GPU/microservices are only for scale (see the bottom).

## Local (laptop) — the default
```bash
make install-serve && make serve      # http://127.0.0.1:8000
```
Runs fully offline (simulated failure-injecting upstream). To use real models: `pip install -e ".[providers]"`
and set `OPENAI_API_KEY` (or run Ollama for the judge). `GET /healthz` shows what's active.

Serve the polished React UI from the same service by building it first:
```bash
make web-build && make serve          # http://127.0.0.1:8000 now serves the Next.js UI at /
```
Without that step, `make serve` serves the built-in lite dashboard — both use the same API.

## Render (free tier) — ONE service, one click
`render.yaml` uses a **multi-stage Docker build** (Node builds the Next.js UI → Python serves it + the API),
so the whole product is a single service — no separate frontend deploy, no CORS.
1. Push to GitHub (done).
2. Render → **New → Blueprint** → pick the repo. It reads `render.yaml`, builds the Dockerfile, and deploys
   one web service. Render injects `$PORT` (the app reads it).
3. Open the URL — React dashboard at `/`, OpenAI API at `/v1`, lite dashboard at `/lite`.

Deploys offline (`CONTROLPLANE_FORCE_SIM=1`). For a **free real judge**, add `GROQ_API_KEY` (free tier) and
remove `CONTROLPLANE_FORCE_SIM`; the T2 judge then routes to Groq automatically.

## Docker — anywhere (also one service)
```bash
docker build -t controlplane .        # builds UI + backend into one image
docker run -p 8000:8000 controlplane  # http://localhost:8000
```

## Vercel (optional — only to put the UI on its own CDN)
Not required: the FastAPI service already serves the UI. If you want the frontend on Vercel, import the repo,
set **Root Directory = `web`** and `NEXT_PUBLIC_API_BASE` = the Render backend URL (CORS is enabled). For the
hackathon, the single Render service above is simpler.

## When you actually need the A100 / AWS microservices
Only for **scale**, not the demo:
- serving a **larger local judge** (or HHEM/MiniCheck) at high QPS,
- running the **full benchmark sweep** (tens of thousands of examples through a 7B model) fast,
- **multi-tenant** isolation, autoscaling, and a real datastore for the flight recorder (SQLite → Postgres).
The code is written so these are swaps behind existing seams (upstream, recorder, detector factory), not a
rewrite — hand them to whoever owns infra.
