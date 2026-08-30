# One container = the whole product: Node builds the Next.js UI to a static export, Python serves it + the
# OpenAI-compatible API. Single service, offline by default (no keys, no model downloads).
#   docker build -t controlplane . ; docker run -p 8000:8000 controlplane   ->  http://localhost:8000

# --- stage 1: build the frontend to a static export (web/out) ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# Static export; the frontend calls the API same-origin, so no API base is baked in.
ENV NEXT_OUTPUT=export NEXT_PUBLIC_API_BASE=
RUN npm run build

# --- stage 2: python backend that serves the API and the built UI ---
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY controlplane ./controlplane
# Committed artifacts the running app reads: the public benchmark (Public benchmarks page), the real
# conformal certificates (Risk guarantee), and the fitted calibration / informativeness. Without these the
# deployed app 404s the benchmark and falls back to synthetic calibration.
COPY artifacts ./artifacts
RUN pip install --no-cache-dir -e ".[serve]"
COPY --from=web /web/out ./web/out

ENV CONTROLPLANE_HOST=0.0.0.0 \
    CONTROLPLANE_FORCE_SIM=1
EXPOSE 8000
CMD ["python", "-m", "controlplane.proxy"]
