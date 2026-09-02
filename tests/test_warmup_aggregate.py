from __future__ import annotations

import asyncio
import json
from pathlib import Path

from controlplane.eval.aggregate import _baseline_from_truth, _cm_dict, run
from controlplane.eval.dataset import synthetic_labeled_dataset
from controlplane.eval.metrics import ConfusionMatrix
from controlplane.startup import ModelWarmup, WarmupState, env_bool


def test_env_bool_parses_truthy_and_falsey(monkeypatch):
    monkeypatch.setenv("CP_TEST_BOOL", "true")
    assert env_bool("CP_TEST_BOOL") is True
    monkeypatch.setenv("CP_TEST_BOOL", "off")
    assert env_bool("CP_TEST_BOOL") is False


def test_env_bool_default(monkeypatch):
    monkeypatch.delenv("CP_TEST_BOOL", raising=False)
    assert env_bool("CP_TEST_BOOL", False) is False
    assert env_bool("CP_TEST_BOOL", True) is True


def test_warmup_disabled_is_immediately_ready():
    warm = ModelWarmup(enabled=False)
    assert warm.snapshot()["ready"] is True
    async def go():
        assert warm.start(service=object()) is None
    asyncio.run(go())
    status = warm.snapshot()
    assert status["status"] == "disabled"
    assert status["ready"] is True


def test_warmup_state_snapshot_has_expected_schema():
    s = WarmupState(enabled=True, status="pending")
    got = s.snapshot()
    assert set(got) == {"enabled", "ready", "status", "elapsed_seconds", "components", "error"}
    assert got["enabled"] is True
    assert got["ready"] is False


def test_warmup_component_records_elapsed_and_status():
    warm = ModelWarmup(enabled=True)
    warm._component("demo", "ready", None)
    snap = warm.snapshot()
    assert snap["components"]["demo"]["status"] == "ready"


def test_warmup_component_records_error():
    warm = ModelWarmup(enabled=True)
    warm._component("demo", "error", "boom")
    item = warm.snapshot()["components"]["demo"]
    assert item["status"] == "error"
    assert item["error"] == "boom"


def test_warmup_can_complete_without_optional_components(monkeypatch):
    warm = ModelWarmup(enabled=True)

    def skip_hhem():
        warm._component("hhem_groundedness", "skipped", "test")
    def skip_cache(service):
        warm._component("semantic_cache", "skipped", "test")

    monkeypatch.setattr(warm, "_warm_hhem", skip_hhem)
    monkeypatch.setattr(warm, "_warm_semantic_cache", skip_cache)

    async def go():
        task = warm.start(service=object())
        assert task is not None
        await task

    asyncio.run(go())
    snap = warm.snapshot()
    assert snap["ready"] is True
    assert snap["status"] == "ready"
    assert snap["error"] is None
    assert set(snap["components"]) == {"hhem_groundedness", "semantic_cache"}


def test_warmup_error_fails_closed(monkeypatch):
    warm = ModelWarmup(enabled=True)

    def bad():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(warm, "_warm_hhem", bad)
    monkeypatch.setattr(
        warm, "_warm_semantic_cache",
        lambda service: warm._component("semantic_cache", "skipped", "test"),
    )

    async def go():
        task = warm.start(service=object())
        assert task is not None
        await task

    asyncio.run(go())
    snap = warm.snapshot()
    assert snap["ready"] is False
    assert snap["status"] == "error"
    assert "model unavailable" in snap["error"]


def test_warmup_start_is_idempotent(monkeypatch):
    warm = ModelWarmup(enabled=True)
    monkeypatch.setattr(warm, "_warm_hhem", lambda: warm._component("hhem", "skipped", "test"))
    monkeypatch.setattr(warm, "_warm_semantic_cache", lambda service: warm._component("cache", "skipped", "test"))

    async def go():
        first = warm.start(service=object())
        second = warm.start(service=object())
        assert first is second
        await first

    asyncio.run(go())


def test_baseline_no_oversight_predicts_no_failures():
    ds = synthetic_labeled_dataset()[:4]
    report = _baseline_from_truth(ds, "no_oversight")
    cm = report.confusion["performance"]
    assert cm["tp"] == 0
    assert cm["fn"] == sum(bool(x.labels.get("performance", False)) for x in ds)


def test_baseline_flag_everything_predicts_all_failures():
    ds = synthetic_labeled_dataset()[:4]
    report = _baseline_from_truth(ds, "flag_everything")
    cm = report.confusion["performance"]
    assert cm["fp"] + cm["tp"] == len(ds)


def test_cm_dict_exposes_counts_and_rates():
    cm = ConfusionMatrix(tp=8, fp=2, fn=2, tn=8)
    d = _cm_dict(cm)
    assert d["tp"] == 8 and d["fp"] == 2
    assert d["recall"] == 0.8
    assert d["precision"] == 0.8
    assert d["f1"] == 0.8


def test_aggregate_report_has_all_strategies():
    ds = synthetic_labeled_dataset()[:6]
    artifact = run(ds, tau=0.5, use_models=False, warmup=1, repeats=2)
    assert set(artifact["strategies"]) == {"no_oversight", "flag_everything", "fixed_checks", "controlplane"}
    assert artifact["methodology"]["same_examples"] is True
    assert artifact["methodology"]["cold_start_excluded_from_latency"] is True


def test_aggregate_controlplane_has_required_metric_columns():
    ds = synthetic_labeled_dataset()[:6]
    artifact = run(ds, tau=0.5, use_models=False, warmup=1, repeats=2)
    cp = artifact["strategies"]["controlplane"]
    perf = cp["confusion"]["performance"]
    resp = cp["confusion"]["responsibility"]
    for d in (perf, resp):
        assert {"tp", "fp", "fn", "tn", "precision", "recall", "f1", "fpr", "fnr", "f1_ci_low", "f1_ci_high"} <= set(d)
    assert {"p50", "p95", "p99", "mean", "samples"} <= set(cp["latency_ms"])


def test_aggregate_repeats_only_expand_latency_samples():
    ds = synthetic_labeled_dataset()[:5]
    artifact = run(ds, tau=0.5, use_models=False, warmup=1, repeats=3)
    cp = artifact["strategies"]["controlplane"]
    assert cp["n"] == len(ds)
    assert cp["latency_ms"]["samples"] == len(ds) * 3


def test_aggregate_warmup_is_excluded_from_reported_sample_count():
    ds = synthetic_labeled_dataset()[:5]
    artifact = run(ds, tau=0.5, use_models=False, warmup=3, repeats=1)
    cp = artifact["strategies"]["controlplane"]
    assert artifact["methodology"]["warmup_samples_excluded"] == 3
    assert cp["latency_ms"]["samples"] == len(ds)


def test_aggregate_latency_percentiles_are_ordered():
    ds = synthetic_labeled_dataset()[:8]
    artifact = run(ds, tau=0.5, use_models=False, warmup=1, repeats=2)
    lat = artifact["strategies"]["controlplane"]["latency_ms"]
    assert lat["p50"] <= lat["p95"] <= lat["p99"]


def test_aggregate_recall_ci_is_bounded():
    ds = synthetic_labeled_dataset()[:8]
    artifact = run(ds, tau=0.5, use_models=False, warmup=1, repeats=1)
    for axis in ("performance", "responsibility"):
        cm = artifact["strategies"]["controlplane"]["confusion"][axis]
        assert 0.0 <= cm["f1_ci_low"] <= cm["f1_ci_high"] <= 1.0


def test_aggregate_output_is_json_serializable(tmp_path):
    ds = synthetic_labeled_dataset()[:5]
    artifact = run(ds, tau=0.5, use_models=False, warmup=1, repeats=1)
    path = tmp_path / "aggregate.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["strategies"]["controlplane"]["name"] == "controlplane"


def test_final_ui_exposes_receipt_verification_and_cache():
    """The UI must actually wire these capabilities up.

    Asserted on the identifiers the UI calls, not on button copy: a wording change is a normal edit and
    should not fail the suite, whereas dropping the call is a real regression.
    """
    root = Path(__file__).resolve().parents[1]
    api = (root / "web/lib/api.ts").read_text(encoding="utf-8")
    ui = (root / "web/components/Dashboard.tsx").read_text(encoding="utf-8")
    assert "verifyReceipt" in api
    assert "cache:" in api
    assert "api.verifyReceipt(" in ui, "the receipt drawer must offer chain verification"
    assert "api.cache(" in ui, "the runtime panel must report cache status"
    assert "api.informativeness(" in ui, "the detectors panel must report learned informativeness"


def test_render_uses_readiness_health_check_and_warmup():
    render = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /readyz" in render
    assert 'key: CONTROLPLANE_WARMUP' in render
    assert 'value: "1"' in render


def test_makefile_exposes_aggregate_eval():
    makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
    assert "eval-aggregate" in makefile
    assert "controlplane.eval.aggregate" in makefile

def test_enabled_warmup_gates_readiness_until_complete(monkeypatch):
    from fastapi.testclient import TestClient

    from controlplane.proxy.app import create_app
    from controlplane.startup import ModelWarmup

    monkeypatch.setenv("CONTROLPLANE_WARMUP", "1")
    monkeypatch.setattr(ModelWarmup, "_warm_hhem", lambda self: self._component("hhem", "skipped", "test"))
    monkeypatch.setattr(
        ModelWarmup, "_warm_semantic_cache",
        lambda self, service: self._component("cache", "skipped", "test"),
    )

    with TestClient(create_app(recorder_path=None, force_simulated=True)) as client:
        response = client.get("/readyz")
        assert response.status_code == 200
        body = response.json()
        assert body["ready"] is True
        assert body["warmup"]["status"] == "ready"
        assert body["warmup"]["components"]["hhem"]["status"] == "skipped"


def test_enabled_warmup_reports_failure_without_claiming_ready(monkeypatch):
    from fastapi.testclient import TestClient

    from controlplane.proxy.app import create_app
    from controlplane.startup import ModelWarmup

    monkeypatch.setenv("CONTROLPLANE_WARMUP", "1")

    def bad(self):
        self._component("hhem", "error", "simulated load failure")
        raise RuntimeError("simulated load failure")

    monkeypatch.setattr(ModelWarmup, "_warm_hhem", bad)
    monkeypatch.setattr(
        ModelWarmup, "_warm_semantic_cache",
        lambda self, service: self._component("cache", "skipped", "test"),
    )

    with TestClient(create_app(recorder_path=None, force_simulated=True)) as client:
        response = client.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert body["warmup"]["status"] == "error"
        assert "simulated load failure" in body["warmup"]["error"]


def test_readyz_remains_compatible_with_existing_contract(monkeypatch):
    monkeypatch.delenv("CONTROLPLANE_WARMUP", raising=False)
    from fastapi.testclient import TestClient

    from controlplane.proxy.app import create_app

    with TestClient(create_app(recorder_path=None, force_simulated=True)) as client:
        body = client.get("/readyz").json()
        assert {"ready", "upstream", "policy_loaded", "recorder", "warmup"} <= set(body)
