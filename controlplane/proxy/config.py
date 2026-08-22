"""Configuration for the ControlPlane proxy.

Environment variables are used so the same application can run locally, in Docker, or in CI
without changing source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProxySettings:
    """Runtime settings for the HTTP gateway."""

    backend: str = "mock"
    upstream_base_url: str = "http://localhost:8001/v1"
    api_key: str = ""
    host: str = "0.0.0.0"
    port: int = 8000
    request_timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> "ProxySettings":
        """Load settings from ``CONTROLPLANE_*`` environment variables."""
        return cls(
            backend=os.getenv("CONTROLPLANE_BACKEND", "mock").strip().lower(),
            upstream_base_url=os.getenv("CONTROLPLANE_UPSTREAM_BASE_URL", "http://localhost:8001/v1").rstrip("/"),
            api_key=os.getenv("CONTROLPLANE_API_KEY", ""),
            host=os.getenv("CONTROLPLANE_HOST", "0.0.0.0"),
            port=int(os.getenv("CONTROLPLANE_PORT", "8000")),
            request_timeout_s=float(os.getenv("CONTROLPLANE_REQUEST_TIMEOUT_S", "60")),
        )
