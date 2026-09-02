"""Receipts must carry the text behind a decision -- redacted, and with the action that was really applied.

A receipt of scores alone is unreviewable: nobody can judge "p_fail 0.98 -> repair" without seeing what was
asked and what the model said. But the transcript must never become a second copy of the data the system
just blocked, and it must name the action the *user* experienced, not the engine's provisional one.
"""

from __future__ import annotations

from controlplane.core.types import Action, CascadeResult, PnlEntry, PolicyProfile
from controlplane.recorder.receipt import build_receipt, compute_hash
from controlplane.recorder.store import JsonlRecorder

CARD = "4111 1111 1111 1111"


def _result(**kw) -> CascadeResult:
    base = dict(request_id="req-1", use_case="support_bot", prompt="p", response="r", model="m")
    return CascadeResult(**{**base, **kw})


def test_transcript_carries_the_text() -> None:
    receipt = build_receipt(
        _result(prompt="What is the refund window?", response="30 days.",
                retrieved_context=["Refunds are available within 30 days."]),
        PnlEntry(), policy_id="p",
    )
    assert receipt.transcript.prompt == "What is the refund window?"
    assert receipt.transcript.response == "30 days."
    assert receipt.transcript.retrieved_context == ["Refunds are available within 30 days."]


def test_transcript_redacts_identifiers_everywhere() -> None:
    """Prompt, response, delivered text and retrieved source all go through the same redactor."""
    receipt = build_receipt(
        _result(
            prompt=f"is {CARD} on file?",
            response=f"yes, the card is {CARD}",
            retrieved_context=[f"Account 1 - card {CARD}"],
        ),
        PnlEntry(), policy_id="p", repaired_output=f"blocked, contained {CARD}",
    )
    t = receipt.transcript
    for field in (t.prompt, t.response, t.delivered, *t.retrieved_context):
        assert "4111" not in field
        assert "[REDACTED_CREDIT_CARD]" in field
    assert t.redacted["credit_card"] == 4  # counted as evidence, without storing the value


def test_transcript_is_length_capped() -> None:
    receipt = build_receipt(_result(response="x" * 5000), PnlEntry(), policy_id="p")
    assert receipt.transcript.truncated is True
    assert len(receipt.transcript.response) < 2000


def test_net_usd_is_serialised() -> None:
    """It is derived, but it must reach the JSON the UI reads -- a bare @property silently did not."""
    dumped = PnlEntry(cost_saved_usd=0.003, safety_spend_usd=0.001).model_dump(mode="json")
    assert dumped["net_usd"] == -0.002


def test_transcript_is_covered_by_the_hash_chain() -> None:
    recorder = JsonlRecorder()
    receipt = recorder.record(_result(response="original"), PnlEntry(), policy_id="p")
    assert recorder.verify_chain()
    receipt.transcript.response = "tampered"
    assert compute_hash(receipt) != receipt.hash_self
    assert not recorder.verify_chain()


def test_recorded_action_is_the_one_the_user_experienced() -> None:
    """The action layer upgrades ESCALATE to AUTO_REPAIR when a faithful correction exists.

    The receipt has to record that upgrade. Otherwise the audit trail says "escalated" beside text that was
    in fact repaired and delivered, and every count built on the log disagrees with what the feed shows.
    """
    from controlplane.core.types import Axis, AxisOutcome
    from controlplane.proxy.actions import apply_action

    policy = PolicyProfile()
    result = _result(action=Action.ESCALATE, retrieved_context=["Refunds are available within 30 days."])
    result.per_axis[Axis.PERFORMANCE] = AxisOutcome(axis=Axis.PERFORMANCE, p_fail=0.9, expected_loss=0.9)
    result.per_axis[Axis.RESPONSIBILITY] = AxisOutcome(axis=Axis.RESPONSIBILITY, p_fail=0.0, expected_loss=0.0)

    applied = apply_action("Refunds take 180 days.", result, policy, result.retrieved_context)
    assert applied.action is Action.AUTO_REPAIR
    assert applied.text == "Refunds are available within 30 days."

    # This mirrors what OversightService.oversee does before recording.
    result.action = applied.action
    receipt = build_receipt(result, PnlEntry(), policy_id="p", repaired_output=applied.text)
    assert receipt.action is Action.AUTO_REPAIR
    assert receipt.transcript.delivered == "Refunds are available within 30 days."


def test_grounded_repair_never_leaks_pii_from_the_source() -> None:
    """Repairing from a source document must not turn a performance fix into a privacy leak."""
    from controlplane.core.types import Axis, AxisOutcome
    from controlplane.proxy.actions import apply_action

    result = _result(action=Action.ESCALATE)
    result.per_axis[Axis.PERFORMANCE] = AxisOutcome(axis=Axis.PERFORMANCE, p_fail=0.9, expected_loss=0.9)
    result.per_axis[Axis.RESPONSIBILITY] = AxisOutcome(axis=Axis.RESPONSIBILITY, p_fail=0.0, expected_loss=0.0)

    applied = apply_action("wrong answer", result, PolicyProfile(), [f"Jane Doe, card {CARD}"])
    assert applied.action is Action.AUTO_REPAIR
    assert "4111" not in applied.text
    assert "[REDACTED_CREDIT_CARD]" in applied.text
    assert "credit_card" in applied.note


def test_auto_repair_refuses_to_choose_between_conflicting_sources() -> None:
    """With several retrieved passages there is no authoritative answer, so a person decides.

    Taking the first chunk is arbitrary: on a knowledge base holding both an old and a current policy it
    silently reinstates the outdated one and presents it to the user as the correction.
    """
    from controlplane.core.types import Axis, AxisOutcome
    from controlplane.proxy.actions import apply_action

    result = _result(action=Action.ESCALATE)
    result.per_axis[Axis.PERFORMANCE] = AxisOutcome(axis=Axis.PERFORMANCE, p_fail=0.9, expected_loss=0.9)
    result.per_axis[Axis.RESPONSIBILITY] = AxisOutcome(axis=Axis.RESPONSIBILITY, p_fail=0.0, expected_loss=0.0)

    conflicting = ["Policy v2.1: refunds within 30 days.", "Policy v3.0 (current): refunds within 14 days."]
    applied = apply_action("refunds take 60 days", result, PolicyProfile(), conflicting)
    assert applied.action is Action.ESCALATE
    assert "30 days" not in applied.text, "must not reinstate the outdated policy as an authoritative fix"

    # A single, unambiguous source still repairs.
    applied = apply_action("refunds take 60 days", result, PolicyProfile(), [conflicting[1]])
    assert applied.action is Action.AUTO_REPAIR
    assert "14 days" in applied.text
