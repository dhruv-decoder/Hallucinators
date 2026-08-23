# ControlPlane — Web (The Tower dashboard)

The product frontend: **Next.js 14 (App Router) + TypeScript + Tailwind + Recharts**. It renders the live
Control-Tower — overview, live feed, confidently-wrong map, Oversight P&L, a latency/scale benchmark (with
progress + ETA), What-If replay, agent oversight, compliance, detectors/models, and a getting-started guide —
against the FastAPI oversight API.

It is a client-side SPA, so it can run **two ways**:

## A) One service (recommended) — served by FastAPI

Build it to a static export; the backend then serves the UI **and** the API from a single origin (no CORS, no
second deploy):

```bash
make web-build      # -> web/out  (NEXT_OUTPUT=export, same-origin API)
make serve          # http://127.0.0.1:8000  serves the React UI at / + the API
```

This is what the Docker image and `render.yaml` do (a multi-stage build: Node builds the UI, Python serves it).

## B) Split dev — Next dev server + backend (hot reload)

```bash
make serve          # backend on :8000 (terminal 1)
cd web && npm install && npm run dev   # UI on :3000 (terminal 2)
```

In dev, `/api/*` is proxied to the backend (`BACKEND_ORIGIN`, default `http://127.0.0.1:8000`) — no CORS hop.

## Configuration (`.env.example`)

- `NEXT_PUBLIC_API_BASE` — leave empty for one-service/static (same-origin) or dev; set it to a remote backend
  origin (e.g. `https://controlplane-tower.onrender.com`) only if you host the frontend separately on Vercel.
- `BACKEND_ORIGIN` — dev-only, for the rewrite proxy.

Scripts: `npm run dev` · `npm run build` · `npm run typecheck` · `npm run lint`. Versions are pinned and
`package-lock.json` is committed for reproducibility.

## Optional: host the frontend on Vercel

Only if you want the UI on its own CDN: import the repo, set **Root Directory = `web`** and
`NEXT_PUBLIC_API_BASE` = your backend URL. The backend still deploys once (see [../docs/DEPLOY.md](../docs/DEPLOY.md)).
For the hackathon, one Render service (option A) is simplest.
