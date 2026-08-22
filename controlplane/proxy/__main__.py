"""Run the ControlPlane proxy with ``python -m controlplane.proxy``."""

from __future__ import annotations

import uvicorn

from controlplane.proxy.config import ProxySettings


if __name__ == "__main__":
    settings = ProxySettings.from_env()
    uvicorn.run("controlplane.proxy.app:app", host=settings.host, port=settings.port, reload=False)
