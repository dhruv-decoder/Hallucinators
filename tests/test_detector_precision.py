"""Precision guards on the detector stack: right entity, right evidence, right winner.

Each test here corresponds to a defect that produced a *plausible-looking but wrong* answer on screen --
the worst kind, because nothing errors and the receipt still reads as authoritative.
"""

from __future__ import annotations

import pytest

from controlplane.cascade.detectors.base import Detector
from controlplane.cascade.detectors.bias import BiasHeuristicDetector
from controlplane.cascade.detectors.responsibility import detect_pii, redact_pii
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile, RequestContext, Tier

VISA = "4111 1111 1111 1111"  # Luhn-valid test card


class TestPiiEntityNaming:
    """A Luhn-valid card also matches the 12-digit Aadhaar pattern, so precedence decides the label."""

    def test_card_is_reported_as_a_card_not_an_aadhaar(self) -> None:
        found = detect_pii(f"the card on file is {VISA} and it is active")
        assert found == {"credit_card": 1}

    def test_a_real_aadhaar_is_still_reported(self) -> None:
        assert detect_pii("Aadhaar 2345 6789 0123 on file") == {"aadhaar": 1}

    def test_typographic_spaces_do_not_hide_a_card(self) -> None:
        """Models format numbers with narrow no-break spaces; an ASCII-only pattern failed open."""
        narrow = VISA.replace(" ", " ")
        assert detect_pii(f"card {narrow} exp 08/27") == {"credit_card": 1}

    def test_redaction_uses_the_same_names_it_flags(self) -> None:
        redacted, counts = redact_pii(f"card {VISA}, email jane.doe@acme.com")
        assert "[REDACTED_CREDIT_CARD]" in redacted
        assert "[REDACTED_EMAIL]" in redacted
        assert "4111" not in redacted
        assert counts == {"credit_card": 1, "email": 1}

    def test_ordinary_numbers_are_not_pii(self) -> None:
        assert detect_pii("The invoice total was 25 dollars in 2024") == {}


class TestBiasDetection:
    def test_age_coded_rationalisation_is_caught(self) -> None:
        """The euphemism a model actually reaches for, written with the punctuation it actually emits."""
        detector = BiasHeuristicDetector()
        score, detail = detector.assess(RequestContext(
            request_id="r",
            response="I’d hire the 27‑year‑old — the older candidate isn’t going to keep up and is set in their ways.",
        ))
        assert detail["bias"] is True
        assert score > 0.5

    def test_neutral_mentions_stay_clean(self) -> None:
        detector = BiasHeuristicDetector()
        for text in [
            "Our diverse team includes men and women from many countries.",
            "Maternity leave is 26 weeks of paid leave under the policy.",
            "Both candidates meet the bar; I recommend a structured system-design interview for each.",
        ]:
            score, detail = detector.assess(RequestContext(request_id="r", response=text))
            assert score == 0.0, text
            assert detail["bias"] is False


class _Fixed(Detector):
    """A detector that returns a preset score, for exercising the engine's combination rule."""

    axis = Axis.PERFORMANCE

    def __init__(self, name: str, tier: Tier, score: float, construct: str = "") -> None:
        self.name = name
        self.tier = tier
        self.construct = construct
        self._score = score
        self.est_cost_usd = 0.0
        self.est_latency_ms = 1.0
        self.informativeness = 0.9

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        return self._score, {}


class TestConstructSupersession:
    """Rival estimates of one construct must not compound: the best tier that ran governs.

    Otherwise the expensive check can only ever *raise* the score, so buying it can never clear a response
    the cheap proxy got wrong -- and three correlated guesses stack into false certainty.
    """

    def _run(self, detectors: list[Detector]) -> float:
        engine = CascadeEngine(detectors=detectors, policy=PolicyProfile(lambda_latency=0.0))
        ctx = RequestContext(request_id="r", prompt="q", response="a", retrieved_context=["src"])
        return engine.run(ctx).per_axis[Axis.PERFORMANCE].p_fail

    def test_expensive_check_supersedes_the_cheap_proxy_it_upgrades(self) -> None:
        p = self._run([
            _Fixed("cheap", Tier.T0, 0.9, construct="groundedness"),
            _Fixed("expensive", Tier.T2, 0.05, construct="groundedness"),
        ])
        assert p == pytest.approx(0.05), "the higher tier's estimate should govern, not compound with the cheap one"

    def test_independent_constructs_still_compound(self) -> None:
        p = self._run([
            _Fixed("groundedness_x", Tier.T0, 0.5, construct="groundedness"),
            _Fixed("other_signal", Tier.T0, 0.5),
        ])
        assert p > 0.5, "genuinely independent evidence should still combine"

    def test_unannotated_detectors_are_unaffected(self) -> None:
        """A detector that declares no construct is its own group, so old behaviour is preserved."""
        p = self._run([_Fixed("a", Tier.T0, 0.5), _Fixed("b", Tier.T0, 0.5)])
        assert p == pytest.approx(0.75)
