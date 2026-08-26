"""The oversight service -- the single object The Tower's endpoints call.

It owns the long-lived pieces (the cascade engine, the P&L ledger, the flight recorder, the adaptive
thermostat, and the active policy profiles) and exposes one method, :meth:`oversee`, that takes a candidate
generation and runs the full inline pipeline:

    generation -> RequestContext -> thermostat scrutiny -> CascadeEngine.run -> PnlLedger.book
               -> apply_action (repair/redact/block) -> recorder.record -> notify UI subscribers

Everything downstream of the engine (the P&L, the receipt, the SSE fan-out) is done here so the HTTP layer
in ``app.py`` stays thin. Concurrency-safety: ``oversee`` holds a lock for the mutating section (ledger
totals, recorder hash chain, thermostat window, subscriber list) so parallel requests can't interleave and
corrupt the chain -- the detectors themselves are pure and run outside the lock.
"""

from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass, field

from controlplane.cascade.detectors.factory import (
    active_models,
    build_cost_detectors,
    build_failure_detectors,
)
from controlplane.cascade.engine import CascadeEngine
from controlplane.cascade.thermostat import Thermostat, risk_score
from controlplane.core.types import (
    Axis,
    PolicyProfile,
    RequestContext,
    VoIReceipt,
)
from controlplane.pnl import PnlLedger
from controlplane.proxy.actions import AppliedAction, apply_action
from controlplane.proxy.jobs import Job, JobRunner
from controlplane.proxy.observability import RuntimeStats
from controlplane.proxy.upstream import Generation
from controlplane.recorder import JsonlRecorder


def default_policies() -> dict[str, PolicyProfile]:
    """Two use-case profiles with different risk appetites (brief A1: different tolerances per use case).

    - ``support_bot`` -- customer-facing, balanced: a wrong refund policy is costly, so it verifies
      performance actively, but it also values low latency.
    - ``internal_copilot`` -- internal engineering assistant: higher tolerance for uncertainty (an engineer
      can sanity-check), lower stakes on a hallucination, so it escalates less and passes more.
    """
    return {
        "support_bot": PolicyProfile(
            id="support_bot@IN@balanced",
            cost_fail={Axis.PERFORMANCE: 1.0, Axis.RESPONSIBILITY: 5.0},
            cost_mitigate={Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10},
            block_threshold=0.85,
            escalate_threshold=0.5,
            annotate_threshold=0.2,
        ),
        "internal_copilot": PolicyProfile(
            id="internal_copilot@IN@lenient",
            cost_fail={Axis.PERFORMANCE: 0.4, Axis.RESPONSIBILITY: 4.0},
            cost_mitigate={Axis.PERFORMANCE: 0.05, Axis.RESPONSIBILITY: 0.10},
            block_threshold=0.9,
            escalate_threshold=0.65,
            annotate_threshold=0.35,
        ),
    }


@dataclass
class OverseeResult:
    """Everything an endpoint needs after oversight: the final text, the receipt, and the applied action."""

    final_text: str
    receipt: VoIReceipt
    applied: AppliedAction
    added_latency_ms: float
    scrutiny: float
    generation: Generation


@dataclass
class _Subscribers:
    """Thread-safe set of live SSE queues for the UI's receipt stream."""

    _qs: list[queue.Queue[VoIReceipt]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self) -> queue.Queue[VoIReceipt]:
        q: queue.Queue[VoIReceipt] = queue.Queue(maxsize=256)
        with self._lock:
            self._qs.append(q)
        return q

    def remove(self, q: queue.Queue[VoIReceipt]) -> None:
        with self._lock:
            if q in self._qs:
                self._qs.remove(q)

    def publish(self, receipt: VoIReceipt) -> None:
        with self._lock:
            targets = list(self._qs)
        for q in targets:
            try:
                q.put_nowait(receipt)
            except queue.Full:
                pass  # a slow UI client drops frames rather than blocking the request path


class OversightService:
    """Long-lived oversight state and the one entry point the proxy endpoints use."""

    def __init__(
        self,
        recorder_path: str | None = "recorder_log.jsonl",
        use_thermostat: bool = True,
    ) -> None:
        # The factory picks the strongest detector stack available here (heuristics offline; HHEM / Presidio
        # / a T2 LLM judge when their deps or a backend are present). The cost cache is stateful -> one shared.
        self.engine = CascadeEngine(
            detectors=build_failure_detectors(),
            cost_detectors=build_cost_detectors(),
        )
        self.ledger = PnlLedger()
        # A ``.db`` path selects the durable SQLite recorder; anything else uses the JSONL reference store.
        # Both share the record / receipts / verify_chain interface, so everything downstream is unchanged.
        if recorder_path and str(recorder_path).endswith(".db"):
            from controlplane.recorder.sqlite_store import SqliteRecorder

            self.recorder = SqliteRecorder(recorder_path)
        else:
            self.recorder = JsonlRecorder(path=recorder_path)
        self.policies = default_policies()
        self.active_policy_key = "support_bot"
        self.thermostat = Thermostat() if use_thermostat else None
        self._subscribers = _Subscribers()
        self._lock = threading.Lock()
        self._request_seq = 0
        self.jobs = JobRunner()
        self.runtime = RuntimeStats()
        self.max_concurrency = max(1, int(os.environ.get("CONTROLPLANE_MAX_CONCURRENCY", "32")))
        self.queue_timeout_ms = max(10, int(os.environ.get("CONTROLPLANE_QUEUE_TIMEOUT_MS", "250")))
        self._request_slots = threading.BoundedSemaphore(self.max_concurrency)
        self.upstream = None  # set by the app so bulk-simulate can generate candidates

    # -- policy --------------------------------------------------------------------------------------
    @property
    def policy(self) -> PolicyProfile:
        return self.policies[self.active_policy_key]

    def set_policy(self, key: str) -> None:
        if key not in self.policies:
            raise KeyError(key)
        self.active_policy_key = key

    def policy_for(self, use_case: str | None) -> tuple[str, PolicyProfile]:
        """Pick the policy for a request: its declared use case if we have a profile, else the active one."""
        if use_case and use_case in self.policies:
            return use_case, self.policies[use_case]
        return self.active_policy_key, self.policy

    def generate_policy(self, spec_dict: dict, apply: bool = False) -> dict:
        """Turn a use-case spec into a tuned policy + projection; optionally register & activate it live."""
        from controlplane.policy import UseCaseSpec, generate_policy

        gen = generate_policy(UseCaseSpec.from_dict(spec_dict))
        if apply:
            self.policies[gen.profile_id] = gen.profile
            self.active_policy_key = gen.profile_id
        return {**gen.to_dict(), "applied": apply}

    # -- the pipeline --------------------------------------------------------------------------------
    def oversee(self, prompt: str, generation: Generation, request_id: str | None = None) -> OverseeResult:
        """Run the full inline oversight pipeline for one candidate generation."""
        import time

        policy_key, policy = self.policy_for(generation.use_case)
        ctx = RequestContext(
            request_id=request_id or self._next_request_id(),
            use_case=generation.use_case,
            prompt=prompt,
            response=generation.text,
            retrieved_context=generation.retrieved_context,
            samples=generation.samples,
            model=generation.model,
            input_tokens=generation.input_tokens,
            output_tokens=generation.output_tokens,
            meta={"injected_failure": generation.injected_failure} if generation.injected_failure else {},
        )

        # Detectors are pure -> run the (potentially slow) cascade outside the lock. Scrutiny is read from
        # the thermostat's current state; the feedback write happens under the lock below.
        scrutiny = self.thermostat.recommend() if self.thermostat else 1.0
        start = time.perf_counter()
        result = self.engine.run(ctx, scrutiny=scrutiny)
        applied = apply_action(generation.text, result, policy, generation.retrieved_context)
        added_latency_ms = (time.perf_counter() - start) * 1000.0

        # Mutating section: ledger totals, recorder hash chain, thermostat window, subscriber fan-out.
        with self._lock:
            pnl = self.ledger.book(ctx, result)
            receipt = self.recorder.record(
                result,
                pnl,
                policy_id=policy.id,
                repaired_output=applied.text if applied.modified else None,
            )
            if self.thermostat:
                self.thermostat.observe(risk_score(result))
            self._subscribers.publish(receipt)

        result_obj = OverseeResult(
            final_text=applied.text,
            receipt=receipt,
            applied=applied,
            added_latency_ms=added_latency_ms,
            scrutiny=scrutiny,
            generation=generation,
        )
        self.runtime.record_result(added_latency_ms, result_obj)
        return result_obj

    def _next_request_id(self) -> str:
        with self._lock:
            self._request_seq += 1
            return f"req-{self._request_seq:05d}"

    # -- agentic trajectory oversight ---------------------------------------------------------------
    def run_agent_demo(self) -> dict:
        """Run the compounding-hallucination trajectory under the auditor, into the live feed + P&L.

        Each executed agent step is recorded as an ordinary receipt (so agent oversight shows up in the same
        feed and audit trail), and the spend avoided by aborting early is booked as cost saved -- the agent
        "waste-killer" contributing to the self-funding P&L.
        """
        from controlplane.agent import TrajectoryAuditor
        from controlplane.agent.scenarios import TASK, compounding_hallucination_trajectory

        policy = self.policies["support_bot"]
        with self._lock:
            auditor = TrajectoryAuditor(policy=policy, recorder=self.recorder)
            before = len(self.recorder.receipts)
            rec = auditor.audit(TASK, compounding_hallucination_trajectory())
            for receipt in self.recorder.receipts[before:]:
                self._subscribers.publish(receipt)
            # The steps we never ran are money saved -> book into the self-funding ledger.
            self.ledger.total_cost_saved += rec.wasted_usd
        return rec.model_dump(mode="json")

    # -- long-running jobs (progress + ETA) ---------------------------------------------------------
    def start_benchmark(self, n: int = 2000, weekly_volume: int = 50_000) -> Job:
        """Kick off the latency/throughput benchmark on a background thread; the UI polls its progress."""
        from controlplane.proxy.benchmark import run_benchmark

        return self.jobs.start("benchmark", total=n, target=lambda job: run_benchmark(job, n, weekly_volume))

    def start_bulk_simulate(self, n: int = 40) -> Job:
        """Replay the demo workload through the real pipeline ``n`` times, feeding the live feed + P&L."""
        from controlplane.proxy.workload import demo_prompts

        prompts = demo_prompts()
        total = n * len(prompts)

        def _run(job: Job) -> dict:
            upstream = self.upstream
            for _ in range(n):
                for p in prompts:
                    gen = upstream.generate(p["prompt"], p.get("model", "controlplane-sim"), use_case=p.get("use_case"))
                    self.oversee(p["prompt"], gen)
                    job.tick(1, message=f"processed {job.done + 1:,}/{total:,} interactions")
            return {"processed": total, **self.summary()}

        return self.jobs.start("simulate", total=total, target=_run)

    def acquire_request_slot(self, wait_ms: int | None = None) -> bool:
        """Acquire a shared admission-control slot for real traffic and runtime probes."""
        timeout_ms = self.queue_timeout_ms if wait_ms is None else max(0, int(wait_ms))
        acquired = self._request_slots.acquire(timeout=timeout_ms / 1000.0)
        if not acquired:
            self.runtime.record_overload()
        return acquired

    def release_request_slot(self) -> None:
        """Release a previously acquired admission-control slot."""
        self._request_slots.release()

    def start_runtime_probe(self, n: int = 120, concurrency: int = 16) -> Job:
        """Measure the same bounded admission path used by live HTTP traffic."""
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        n = max(1, min(int(n), 1000))
        concurrency = max(1, min(int(concurrency), 64))

        def _run(job: Job) -> dict:
            prompt = "What are your customer support hours?"
            upstream = self.upstream
            started = time.perf_counter()
            latencies: list[float] = []
            rejected = 0
            errors = 0

            def one(_: int):
                if not self.acquire_request_slot(wait_ms=0):
                    return ("rejected", 0.0, "concurrency limit reached")

                self.runtime.request_started()
                t0 = time.perf_counter()
                try:
                    gen = upstream.generate(prompt, "controlplane-sim", use_case="support_bot")
                    self.oversee(prompt, gen)
                    return ("ok", (time.perf_counter() - t0) * 1000.0, "")
                except Exception as exc:  # pragma: no cover - defensive probe accounting
                    self.runtime.record_error()
                    return ("error", 0.0, str(exc))
                finally:
                    self.runtime.request_finished()
                    self.release_request_slot()

            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(one, i) for i in range(n)]
                for i, fut in enumerate(as_completed(futures), 1):
                    status, latency, _ = fut.result()
                    if status == "ok":
                        latencies.append(latency)
                    elif status == "rejected":
                        rejected += 1
                    else:
                        errors += 1
                    job.tick(1, message=f"completed {i:,}/{n:,} requests")

            elapsed = time.perf_counter() - started
            return {
                "requests": n,
                "concurrency": concurrency,
                "accepted": len(latencies),
                "rejected_overload": rejected,
                "errors": errors,
                "elapsed_seconds": round(elapsed, 3),
                "throughput_rps": round(len(latencies) / elapsed, 2) if elapsed else 0.0,
                "latency_ms": {
                    "p50": round(RuntimeStats._percentile(latencies, 50), 3),
                    "p95": round(RuntimeStats._percentile(latencies, 95), 3),
                    "p99": round(RuntimeStats._percentile(latencies, 99), 3),
                },
                "configured_max_concurrency": self.max_concurrency,
                "queue_timeout_ms": self.queue_timeout_ms,
            }

        return self.jobs.start("runtime_probe", total=n, target=_run)

    # -- UI feeds ------------------------------------------------------------------------------------
    def subscribe(self) -> queue.Queue[VoIReceipt]:
        return self._subscribers.add()

    def unsubscribe(self, q: queue.Queue[VoIReceipt]) -> None:
        self._subscribers.remove(q)

    def summary(self) -> dict:
        """Aggregate state for the dashboard header + P&L card."""
        totals = self.ledger.totals()
        receipts = self.recorder.receipts
        by_action: dict[str, int] = {}
        for r in receipts:
            by_action[r.action.value] = by_action.get(r.action.value, 0) + 1
        cleared_at_t0 = sum(1 for r in receipts if not any(s.ran and int(s.tier) > 0 for s in r.trace))
        n = len(receipts)
        return {
            "requests": n,
            "cost_saved_usd": round(totals.cost_saved_usd, 6),
            "safety_spend_usd": round(totals.safety_spend_usd, 6),
            "net_usd": round(totals.net_usd, 6),
            "self_funding": totals.net_usd < 0,
            "by_action": by_action,
            "cleared_at_t0_pct": round(100.0 * cleared_at_t0 / n, 1) if n else 100.0,
            "scrutiny": round(self.thermostat.scrutiny, 3) if self.thermostat else 1.0,
            "chain_valid": self.recorder.verify_chain(),
            "active_policy": self.policy.id,
            "policies": {k: v.id for k, v in self.policies.items()},
            "models": active_models(),
            "runtime": {**self.runtime.snapshot(), "config": {"max_concurrency": self.max_concurrency, "queue_timeout_ms": self.queue_timeout_ms}},
        }
