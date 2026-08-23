"""A tiny background-job runner with progress + ETA, for operations that take a noticeable moment.

Enterprise UX rule (2026): when something takes time, tell the user how far along it is and how long is left,
and let them watch it. Long operations here (a large-scale latency benchmark, a big simulated workload, a
dataset eval) run in a background thread and report ``progress`` (0-1), an ``eta_seconds`` estimate, and a
human-readable ``message``. The UI polls ``GET /v1/oversight/jobs/{id}`` and renders a real progress bar.

Deliberately dependency-free and thread-based: no Celery/Redis for a laptop-first prototype. Jobs are kept in
memory; that is the honest scope for a demo.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Job:
    """One background job. ``target`` calls :meth:`tick` as it progresses and returns the result dict."""

    id: str
    kind: str
    total: int
    done: int = 0
    status: str = "running"  # running | done | error
    message: str = ""
    result: dict | None = None
    error: str | None = None
    started_at: float = field(default_factory=time.perf_counter)
    finished_at: float | None = None

    def tick(self, n: int = 1, message: str | None = None) -> None:
        self.done = min(self.done + n, self.total)
        if message is not None:
            self.message = message

    @property
    def progress(self) -> float:
        return 1.0 if self.total == 0 else min(self.done / self.total, 1.0)

    @property
    def eta_seconds(self) -> float | None:
        """Linear ETA from throughput so far. None until there is enough signal or once finished."""
        if self.status != "running" or self.done <= 0:
            return None
        elapsed = time.perf_counter() - self.started_at
        rate = self.done / elapsed
        if rate <= 0:
            return None
        return max((self.total - self.done) / rate, 0.0)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 4),
            "done": self.done,
            "total": self.total,
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else None,
            "elapsed_seconds": round((self.finished_at or time.perf_counter()) - self.started_at, 2),
            "message": self.message,
            "result": self.result,
            "error": self.error,
        }


class JobRunner:
    """Starts jobs on background threads and hands out their live snapshots."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, total: int, target: Callable[[Job], dict]) -> Job:
        job = Job(id=f"job-{uuid.uuid4().hex[:10]}", kind=kind, total=total)
        with self._lock:
            self._jobs[job.id] = job

        def _run() -> None:
            try:
                job.result = target(job)
                job.status = "done"
                job.done = job.total
                job.message = job.message or "complete"
            except Exception as exc:  # noqa: BLE001 - surface the failure to the UI, don't crash the server
                job.status = "error"
                job.error = str(exc)
            finally:
                job.finished_at = time.perf_counter()

        threading.Thread(target=_run, daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)
