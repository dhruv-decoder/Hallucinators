import asyncio
import time

import pytest

from controlplane.cascade.async_engine import run_detectors_parallel
from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, PolicyProfile, Tier
from controlplane.cascade.engine import CascadeEngine
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.harness import run_harness
from controlplane.demo.run_demo import build_engine
from controlplane.proxy.oversight import OversightService, monitored_stream
from controlplane.policy import PolicyManager
from controlplane.recorder import SQLiteFlightRecorder


class SlowDetector(Detector):
    axis = Axis.PERFORMANCE
    tier = Tier.T0
    est_latency_ms = 30.0

    def __init__(self, name: str, delay: float):
        self.name = name
        self.delay = delay

    def assess(self, ctx):
        time.sleep(self.delay)
        return 0.0, {}


def test_parallel_detector_execution_is_wall_clock_bounded():
    async def run():
        detectors = [SlowDetector("a", 0.05), SlowDetector("b", 0.05)]
        started = time.perf_counter()
        done, timed_out, elapsed = await run_detectors_parallel(detectors, RequestContext(request_id="x"), timeout_ms=200)
        wall = (time.perf_counter() - started) * 1000
        assert len(done) == 2
        assert not timed_out
        assert wall < 95
        assert elapsed < 95
    asyncio.run(run())


def test_parallel_detector_timeout_is_recorded():
    async def run():
        detectors = [SlowDetector("slow", 0.15)]
        done, timed_out, _ = await run_detectors_parallel(detectors, RequestContext(request_id="x"), timeout_ms=10)
        assert not done
        assert len(timed_out) == 1
    asyncio.run(run())


def test_async_cascade_respects_latency_budget():
    engine = CascadeEngine(
        detectors=[SlowDetector("slow-a", 0.08), SlowDetector("slow-b", 0.08)],
        policy=PolicyProfile(),
    )

    async def run():
        result = await engine.run_async(RequestContext(request_id="budget"), latency_budget_ms=10)
        assert "budget_ms=10.00" in result.stopping_reason
        assert any(step.reason in {"latency_budget_exhausted", "tier_timeout"} for step in result.trace)
    asyncio.run(run())


@pytest.mark.asyncio
async def test_mid_stream_abort_records_partial_receipt(tmp_path):
    recorder = SQLiteFlightRecorder(tmp_path / "abort.db")
    (tmp_path / "policies.yaml").write_text("""version: 1\nprofiles:\n  - id: default@balanced\n    use_case: default\n    geography: \"*\"\n    risk_appetite: balanced\n    cost_fail: {performance: 1.0, responsibility: 5.0}\n    cost_mitigate: {performance: 0.05, responsibility: 0.1}\n    lambda_latency: 0.000001\n    block_threshold: 0.85\n    escalate_threshold: 0.5\n    annotate_threshold: 0.2\n    tier_ceilings: {performance: 2, cost: 0, responsibility: 2}\n""")
    manager = PolicyManager(tmp_path / "policies.yaml")
    service = OversightService(manager, recorder)

    async def source():
        yield b'data: {"choices":[{"delta":{"content":"customer card 4111 "}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"content":"1111 1111 1111"}}]}\n\n'
        yield b'data: [DONE]\n\n'

    out = []
    async for chunk in monitored_stream(
        source(), service=service, request_id="stream-abort", payload={"messages":[{"role":"user","content":"hi"}]},
        model="mock", use_case="default", geography="*", risk_appetite="balanced",
        abort_predicate=service.should_abort_stream,
    ):
        out.append(chunk)
    assert any(b"[DONE]" in chunk for chunk in out)
    receipt = recorder.get("stream-abort")
    assert receipt is not None
    assert recorder.verify_chain()
    recorder.close()


def test_eval_runner_reports_verify_all_and_latency(tmp_path):
    report = run_harness(lambda: build_engine(PolicyProfile(id="eval@balanced")), synthetic_labeled_dataset(), json_path=tmp_path / "report.json")
    assert "controlplane" in report.strategies
    assert "verify_all" in report.strategies
    assert report.cost["p95_added_latency_ms"] >= 0
    assert (tmp_path / "report.json").exists()
