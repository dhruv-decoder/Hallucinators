"""Model warm-up and readiness state for the ControlPlane service.

Warm-up is intentionally opt-in. The normal local/offline service remains fast to start when
CONTROLPLANE_WARMUP is unset/disabled, while Render can enable it so model-backed detectors and
semantic embeddings are initialized before the instance is declared ready for traffic.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class WarmupState:
    enabled: bool = False
    started_at: float | None = None
    finished_at: float | None = None
    ready: bool = False
    status: str = "disabled"
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: str | None = None

    @property
    def elapsed_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at if self.finished_at is not None else time.perf_counter()
        return round(end - self.started_at, 3)

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "status": self.status,
            "elapsed_seconds": self.elapsed_seconds,
            "components": self.components,
            "error": self.error,
        }


class ModelWarmup:
    """Thread-safe readiness state plus an asynchronous warm-up runner."""

    def __init__(self, *, enabled: bool) -> None:
        self.state = WarmupState(enabled=enabled, status="pending" if enabled else "disabled", ready=not enabled)
        self._lock = threading.RLock()
        self._task: asyncio.Task | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.snapshot()

    def start(self, *, service: Any) -> asyncio.Task | None:
        """Start warm-up once; returns the task so lifespan code can keep it alive."""
        if not self.state.enabled:
            with self._lock:
                self.state.ready = True
            return None
        if self._task and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self._run(service))
        return self._task

    async def _run(self, service: Any) -> None:
        with self._lock:
            self.state.started_at = time.perf_counter()
            self.state.status = "warming"
        try:
            tasks = [
                asyncio.to_thread(self._warm_hhem),
                asyncio.to_thread(self._warm_semantic_cache, service),
            ]
            # Components are independent; run them concurrently without blocking the event loop.
            await asyncio.gather(*tasks)
            with self._lock:
                self.state.ready = True
                self.state.status = "ready"
                self.state.finished_at = time.perf_counter()
        except Exception as exc:  # noqa: BLE001 - readiness must fail closed
            with self._lock:
                self.state.ready = False
                self.state.status = "error"
                self.state.error = f"{type(exc).__name__}: {exc}"
                self.state.finished_at = time.perf_counter()

    def _warm_hhem(self) -> None:
        from controlplane.cascade.detectors.groundedness_model import HHEMGroundednessDetector, _get_model

        if not HHEMGroundednessDetector.available():
            self._component("hhem_groundedness", "skipped", "optional dependencies unavailable")
            return
        started = time.perf_counter()
        try:
            _get_model()
            self._component("hhem_groundedness", "ready", None, started)
        except Exception as exc:  # noqa: BLE001
            self._component("hhem_groundedness", "error", f"{type(exc).__name__}: {exc}", started)
            raise

    def _warm_semantic_cache(self, service: Any) -> None:
        cache = getattr(service, "semantic_cache", None)
        if cache is None or not getattr(cache, "enabled", False):
            self._component("semantic_cache", "skipped", "disabled")
            return
        started = time.perf_counter()
        try:
            embedder = cache._get_embedder()  # intentionally warm the same lazy path used by requests
            if embedder is None:
                self._component("semantic_cache", "skipped", "embedding backend unavailable", started)
                return
            embedder("controlplane warmup")
            self._component("semantic_cache", "ready", None, started)
        except Exception as exc:  # noqa: BLE001
            self._component("semantic_cache", "error", f"{type(exc).__name__}: {exc}", started)
            raise

    def _component(self, name: str, status: str, error: str | None, started: float | None = None) -> None:
        elapsed = None if started is None else round(time.perf_counter() - started, 3)
        with self._lock:
            value = {"status": status}
            if elapsed is not None:
                value["elapsed_seconds"] = elapsed
            if error:
                value["error"] = error
            self.state.components[name] = value
