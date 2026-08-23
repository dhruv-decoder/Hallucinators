# The Tower — one container that serves the OpenAI-compatible proxy + the Control-Tower dashboard.
# Offline by default (no keys, no model downloads). Build: docker build -t controlplane . ; run: docker run -p 8000:8000 controlplane
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY controlplane ./controlplane
RUN pip install --no-cache-dir -e ".[serve]"

ENV CONTROLPLANE_HOST=0.0.0.0 \
    CONTROLPLANE_FORCE_SIM=1
EXPOSE 8000
CMD ["python", "-m", "controlplane.proxy"]
