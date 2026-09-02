"""A response that declines to answer must not be scored as a hallucination.

This is the precision fix that makes the whole product defensible: without it, groundedness detectors score
a refusal as maximally unsupported (a refusal shares no words with the source and is not entailed by it), and
the proxy then "repairs" a correct refusal by overwriting it with raw source text -- punishing the single most
desirable model behaviour.
"""

from __future__ import annotations

import pytest

from controlplane.cascade.detectors.abstention import is_abstention, split_abstention
from controlplane.cascade.detectors.judge import LlmJudgeDetector
from controlplane.cascade.detectors.performance import GroundednessHeuristicDetector
from controlplane.core.types import RequestContext

SOURCE = ["Refunds are available within 30 days of purchase, with a valid receipt."]


@pytest.mark.parametrize(
    "text",
    [
        "I'm sorry, but I don't have that information.",
        # Models emit curly apostrophes; an ASCII-only pattern silently never matched, which is exactly how
        # a correct refusal ended up scored as a maximal groundedness failure.
        "I’m sorry, but I can’t provide that.",
        "I cannot provide that information.",
        "That information is not available in the source provided.",
    ],
)
def test_pure_refusals_are_recognised(text: str) -> None:
    assert is_abstention(text)
    assert split_abstention(text)[0] == ""


@pytest.mark.parametrize(
    "text",
    [
        "Refunds are available within 30 days of purchase.",
        "The refund window is 180 days, guaranteed, no doubt about it.",
        "You have 30 days to return a damaged item, and there is no restocking fee.",
    ],
)
def test_claims_are_not_mistaken_for_refusals(text: str) -> None:
    """A confident wrong answer must never be waved through as an abstention."""
    assert not is_abstention(text)
    assert split_abstention(text)[0] == text


def test_partial_answer_keeps_only_the_checkable_claim() -> None:
    text = (
        "Our refund window is within 30 days of purchase. "
        "I don’t have a phone number for the refunds team to share."
    )
    claim, declined = split_abstention(text)
    assert declined, "the refusal clause should be separated out"
    assert "30 days" in claim
    assert "phone number" not in claim


def test_groundedness_abstains_on_a_refusal() -> None:
    """Score 0 *and* an abstained flag, so the engine treats it as no evidence rather than as safety."""
    detector = GroundednessHeuristicDetector()
    ctx = RequestContext(request_id="r", response="I'm sorry, but I don't have that information.",
                         retrieved_context=SOURCE)
    score, detail = detector.assess(ctx)
    assert score == 0.0
    assert detail.get("abstained") is True


def test_groundedness_still_flags_an_ungrounded_claim() -> None:
    detector = GroundednessHeuristicDetector()
    ctx = RequestContext(request_id="r", retrieved_context=SOURCE,
                         response="Refunds take exactly 14 business days to reach your bank account.")
    score, detail = detector.assess(ctx)
    assert score > 0.4
    assert not detail.get("abstained")


def test_judge_abstains_on_a_refusal_without_calling_the_backend() -> None:
    """The judge supersedes the cheaper tiers, so a refusal must short-circuit before it can veto them."""
    judge = LlmJudgeDetector(backend="groq", model="test")

    def _boom(_prompt: str) -> str:  # pragma: no cover - must never be reached
        raise AssertionError("the judge should not call its backend for a refusal")

    judge._call_backend = _boom  # type: ignore[method-assign]
    score, detail = judge.assess(
        RequestContext(request_id="r", response="I’m sorry, but I can’t help with that.",
                       retrieved_context=SOURCE)
    )
    assert score == 0.0
    assert detail.get("abstained") is True


def test_judge_scores_the_claim_not_the_refusal_wrapper() -> None:
    """A partial answer is verified on its claim alone, so 'incomplete' is never scored as 'wrong'."""
    judge = LlmJudgeDetector(backend="groq", model="test")
    seen: dict[str, str] = {}

    def _capture(prompt: str) -> str:
        seen["prompt"] = prompt
        return "0"

    judge._call_backend = _capture  # type: ignore[method-assign]
    judge.assess(
        RequestContext(
            request_id="r",
            retrieved_context=SOURCE,
            response=("Refunds are available within 30 days. "
                      "I don’t have a phone number for the refunds team."),
        )
    )
    answer = seen["prompt"].split("ANSWER:", 1)[1]
    assert "30 days" in answer
    assert "phone number" not in answer
