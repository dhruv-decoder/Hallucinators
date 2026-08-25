"""Bounded in-process runtime telemetry for the ControlPlane demo service."""
from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque


class RuntimeStats:
    """Thread-safe counters and recent latency samples; intentionally dependency-free and bounded."""

    def __init__(self, max_samples: int = 2000) -> None:
        self._lock = threading.Lock()
        self._latencies = deque(maxlen=max_samples)
        self._request_count = 0
        self._active = 0
        self._errors = 0
        self._overload_rejections = 0
        self._stream_aborts = 0
        self._actions = Counter()
        self._detector_calls = Counter()
        self._detector_latency_ms = Counter()
        self._tier_counts = Counter()
        self._started_at = time.time()
        self.max_concurrency = 0

    def request_started(self) -> None:
        with self._lock:
            self._request_count += 1
            self._active += 1
            self.max_concurrency = max(self.max_concurrency, self._active)

    def request_finished(self) -> None:
        with self._lock:
            self._active = max(self._active - 1, 0)

    def record_result(self, elapsed_ms: float, result=None, *, stream_abort: bool = False) -> None:
        with self._lock:
            self._latencies.append(float(elapsed_ms))
            if result is not None:
                try:
                    self._actions[result.applied.action.value] += 1
                    for signal in result.receipt.signals:
                        self._detector_calls[signal.name] += 1
                        self._detector_latency_ms[signal.name] += float(signal.latency_ms)
                        self._tier_counts[f"T{int(signal.tier)}"] += 1
                except AttributeError:
                    pass
            if stream_abort:
                self._stream_aborts += 1

    def record_error(self) -> None:
        with self._lock:
            self._errors += 1

    def record_overload(self) -> None:
        with self._lock:
            self._overload_rejections += 1

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        if len(values) == 1:
            return values[0]
        rank = (p / 100.0) * (len(values) - 1)
        lo = math.floor(rank)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (rank - lo)

    def snapshot(self) -> dict:
        with self._lock:
            latencies = list(self._latencies)
            uptime = max(time.time() - self._started_at, 0.001)
            detector_calls = dict(self._detector_calls)
            detector_avg = {
                name: round(self._detector_latency_ms[name] / calls, 3)
                for name, calls in detector_calls.items()
                if calls
            }
            return {
                "uptime_seconds": round(uptime, 1),
                "requests": self._request_count,
                "active_requests": self._active,
                "throughput_rps": round(self._request_count / uptime, 3),
                "errors": self._errors,
                "overload_rejections": self._overload_rejections,
                "stream_aborts": self._stream_aborts,
                "max_concurrency": self.max_concurrency,
                "latency_ms": {
                    "p50": round(self._percentile(latencies, 50), 3),
                    "p95": round(self._percentile(latencies, 95), 3),
                    "p99": round(self._percentile(latencies, 99), 3),
                    "sample_count": len(latencies),
                },
                "actions": dict(self._actions),
                "tier_counts": dict(self._tier_counts),
                "detector_calls": detector_calls,
                "detector_avg_latency_ms": detector_avg,
            }
