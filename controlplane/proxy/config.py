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
    recorder_db_path: str = "controlplane.db"
    policy_path: str = "policies/policies.yaml"
    default_use_case: str = "default"
    default_geography: str = "*"
    default_risk_appetite: str = "balanced"
    oversight_enabled: bool = True
    latency_budget_ms: float = 100.0
    tier_timeout_t0_ms: float = 25.0
    tier_timeout_t1_ms: float = 75.0
    tier_timeout_t2_ms: float = 250.0
    stream_abort_enabled: bool = True

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
            recorder_db_path=os.getenv("CONTROLPLANE_RECORDER_DB_PATH", "controlplane.db"),
            policy_path=os.getenv("CONTROLPLANE_POLICY_PATH", "policies/policies.yaml"),
            default_use_case=os.getenv("CONTROLPLANE_USE_CASE", "default"),
            default_geography=os.getenv("CONTROLPLANE_GEOGRAPHY", "*"),
            default_risk_appetite=os.getenv("CONTROLPLANE_RISK_APPETITE", "balanced"),
            oversight_enabled=os.getenv("CONTROLPLANE_OVERSIGHT_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            latency_budget_ms=float(os.getenv("CONTROLPLANE_LATENCY_BUDGET_MS", "100")),
            tier_timeout_t0_ms=float(os.getenv("CONTROLPLANE_TIER_TIMEOUT_T0_MS", "25")),
            tier_timeout_t1_ms=float(os.getenv("CONTROLPLANE_TIER_TIMEOUT_T1_MS", "75")),
            tier_timeout_t2_ms=float(os.getenv("CONTROLPLANE_TIER_TIMEOUT_T2_MS", "250")),
            stream_abort_enabled=os.getenv("CONTROLPLANE_STREAM_ABORT_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
        )
