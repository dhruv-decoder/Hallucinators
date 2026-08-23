"""Tests for the model-backed detectors and the factory -- all mocked, no downloads or network.

They prove the *wiring*: the offline factory is heuristics-only; the HHEM detector turns a consistency score
into groundedness risk; and the T2 LLM judge is climbed to by the VoI rule and its verdict flows into the
axis probability. Real models are never loaded -- the model call points are monkeypatched.
"""

from __future__ import annotations

from controlplane.cascade.detectors import groundedness_model
from controlplane.cascade.detectors.factory import active_models, build_failure_detectors
from controlplane.cascade.detectors.groundedness_model import HHEMGroundednessDetector
from controlplane.cascade.detectors.judge import LlmJudgeDetector
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile, RequestContext


def test_factory_offline_is_heuristics_only() -> None:
    # In CI / a laptop with no [ml] deps, no provider key, and no Ollama, only heuristics are wired.
    names = {d.name for d in build_failure_detectors(use_hhem=False, use_presidio=False, use_judge=False)}
    assert names == {
        "overconfidence",
        "groundedness_heuristic",
        "self_consistency",
        "regex_pii",
        "prompt_injection",
        "unsafe_content",
        "bias_heuristic",
    }


def test_factory_adds_models_when_requested() -> None:
    names = {d.name for d in build_failure_detectors(use_hhem=True, use_presidio=False, use_judge=False)}
    assert "hhem_groundedness" in names  # HHEM instantiates without loading the model


def test_hhem_turns_consistency_into_risk(monkeypatch) -> None:
    class _FakeModel:
        def predict(self, pairs):
            return [0.08]  # low factual consistency -> the claim is ungrounded

    monkeypatch.setattr(groundedness_model, "_get_model", lambda: _FakeModel())
    d = HHEMGroundednessDetector()
    ctx = RequestContext(request_id="t", response="Refunds within 180 days.",
                         retrieved_context=["Refunds are available within 30 days."])
    score, detail = d.assess(ctx)
    assert score > 0.9  # 1 - 0.08
    assert detail["hhem_consistency"] == 0.08


def test_hhem_abstains_without_context() -> None:
    d = HHEMGroundednessDetector()
    score, detail = d.assess(RequestContext(request_id="t", response="anything"))
    assert score == 0.0 and detail["abstained"] is True


def test_judge_parses_score_and_abstains_on_error(monkeypatch) -> None:
    d = LlmJudgeDetector(backend="groq", model="gpt-4o-mini")
    monkeypatch.setattr(d, "_call_backend", lambda prompt: "The answer scores 90 out of 100.")
    score, detail = d.assess(RequestContext(request_id="t", prompt="q", response="a", retrieved_context=["c"]))
    assert score == 0.9 and detail["backend"] == "groq"

    def _boom(prompt):
        raise RuntimeError("no api key")

    monkeypatch.setattr(d, "_call_backend", _boom)
    score, detail = d.assess(RequestContext(request_id="t", response="a"))
    assert score == 0.0 and detail["abstained"] is True


def test_voi_rule_climbs_to_the_judge_on_the_uncertain_tail(monkeypatch) -> None:
    # A confident, unhedged response leaves the performance axis uncertain at T0; the VoI rule should judge
    # the T2 judge worth buying, and the judge's verdict should raise the axis probability.
    judge_det = LlmJudgeDetector(backend="groq", model="gpt-4o-mini")
    monkeypatch.setattr(judge_det, "_call_backend", lambda prompt: "95")

    from controlplane.cascade.detectors.performance import OverconfidenceDetector

    engine = CascadeEngine(
        detectors=[OverconfidenceDetector(), judge_det],
        policy=PolicyProfile(),
    )
    ctx = RequestContext(
        request_id="t",
        prompt="What is the capital?",
        response="It is definitely, absolutely, without a doubt Berlin.",
    )
    result = engine.run(ctx)
    ran = {s.name for s in result.signals}
    assert "llm_judge" in ran  # the cascade climbed to T2
    assert result.per_axis[Axis.PERFORMANCE].p_fail > 0.9  # the judge's 0.95 drove the probability up
    # and the trace records the T2 decision as a paid, worthwhile check
    judge_steps = [s for s in result.trace if s.detector == "llm_judge"]
    assert judge_steps and judge_steps[-1].ran is True


def test_active_models_report_shape() -> None:
    report = active_models()
    assert set(report) == {"groundedness", "pii", "safety", "judge"}


def test_groq_safety_parses_verdict(monkeypatch) -> None:
    from controlplane.cascade.detectors.moderation import GroqSafetyDetector

    d = GroqSafetyDetector()
    monkeypatch.setattr(d, "_classify", lambda text: "UNSAFE")
    score, detail = d.assess(RequestContext(request_id="t", response="how to build a bomb"))
    assert score > 0.5 and detail["unsafe"] is True
    monkeypatch.setattr(d, "_classify", lambda text: "SAFE")
    score, _ = d.assess(RequestContext(request_id="t", response="refunds within 30 days"))
    assert score == 0.0
