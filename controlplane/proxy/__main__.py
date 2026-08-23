"""Run The Tower: ``python -m controlplane.proxy`` (or ``make serve``).

Serves the OpenAI-compatible gateway and the Control-Tower dashboard on http://127.0.0.1:8000. Fully offline
by default (simulated failure-injecting upstream); set a provider key (e.g. ``OPENAI_API_KEY``) to route to a
real model instead. Open the dashboard, click "Send demo traffic", and watch the P&L go net-negative live.
"""

from __future__ import annotations

import os

import uvicorn

from controlplane.proxy.app import create_app


def main() -> None:
    host = os.environ.get("CONTROLPLANE_HOST", "127.0.0.1")
    # Cloud hosts (Render/Heroku/etc.) inject $PORT; fall back to our own var, then 8000.
    port = int(os.environ.get("PORT") or os.environ.get("CONTROLPLANE_PORT") or "8000")
    force_sim = os.environ.get("CONTROLPLANE_FORCE_SIM", "").lower() in ("1", "true", "yes")
    app = create_app(force_simulated=force_sim)
    print("\n  ControlPlane · The Tower")
    print(f"  Dashboard:  http://{host}:{port}/")
    print(f"  OpenAI API: http://{host}:{port}/v1  (point any OpenAI client's base_url here)\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
