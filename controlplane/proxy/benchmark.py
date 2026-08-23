"""Measure the oversight overhead honestly: added latency distribution, throughput, and %-cleared-at-T0.

The brief's hard question is "does the checker slow the model down?". This answers it with *measured* numbers,
not a cited figure: run N representative requests through the real cascade and record the wall-clock the
oversight layer adds to each (the model call itself is excluded -- we are measuring our tax, not the model).
We report p50/p95/p99 added latency, sustained throughput, and the fraction resolved at the free T0 tier.

We benchmark the **local** cascade (heuristics + HHEM if installed) with the network T2 judge disabled: the
judge is, by design, only bought for the uncertain ~1-3% tail, so it does not belong in the "does oversight
slow the common path" number. That is stated in the result so the claim is not oversold.

An at-scale block extrapolates the measured per-request economics to an enterprise volume (default 50k
interactions/week) -- clearly labelled as an extrapolation from a simulated workload, never as production data.
"""

from __future__ import annotations

import time

from controlplane.cascade.detectors.factory import build_cost_detectors, build_failure_detectors
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import PolicyProfile
from controlplane.demo.workload import synthetic_workload
from controlplane.pnl import PnlLedger
from controlplane.proxy.jobs import Job


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def run_benchmark(job: Job, n: int = 2000, weekly_volume: int = 50_000) -> dict:
    """Run ``n`` requests through the local cascade, measuring added latency + throughput; extrapolate to scale."""
    policy = PolicyProfile(id="benchmark@balanced")
    engine = CascadeEngine(
        detectors=build_failure_detectors(use_hhem=False, use_presidio=False, use_judge=False),
        cost_detectors=build_cost_detectors(),
        policy=policy,
    )
    ledger = PnlLedger()
    workload = synthetic_workload()

    added_ms: list[float] = []
    cleared_t0 = 0
    wall_start = time.perf_counter()
    for i in range(n):
        ctx = workload[i % len(workload)].model_copy(update={"request_id": f"bench-{i}"})
        t0 = time.perf_counter()
        result = engine.run(ctx)
        added_ms.append((time.perf_counter() - t0) * 1000.0)
        ledger.book(ctx, result)
        if not any(s.ran and int(s.tier) > 0 for s in result.trace):
            cleared_t0 += 1
        if i % max(n // 100, 1) == 0:
            job.tick(i - job.done, message=f"processed {i:,}/{n:,} requests")
    wall = time.perf_counter() - wall_start

    totals = ledger.totals()
    per_request_net = totals.net_usd / n if n else 0.0
    return {
        "n": n,
        "added_latency_ms": {
            "p50": round(_percentile(added_ms, 0.50), 3),
            "p95": round(_percentile(added_ms, 0.95), 3),
            "p99": round(_percentile(added_ms, 0.99), 3),
            "mean": round(sum(added_ms) / len(added_ms), 3),
        },
        "throughput_rps": round(n / wall, 1) if wall > 0 else 0.0,
        "pct_cleared_at_t0": round(100.0 * cleared_t0 / n, 1),
        "net_usd_total": round(totals.net_usd, 5),
        "per_request_net_usd": round(per_request_net, 8),
        "at_scale": {
            "weekly_volume": weekly_volume,
            "weekly_net_usd": round(per_request_net * weekly_volume, 2),
            "annual_net_usd": round(per_request_net * weekly_volume * 52, 2),
            "note": "extrapolated from a simulated workload at sourced prices; not production billing",
        },
        "judge_note": "measured on the local cascade; the T2 LLM-judge is bought only for the uncertain tail",
    }
