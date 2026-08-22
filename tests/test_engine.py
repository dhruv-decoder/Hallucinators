"""End-to-end tests for the cascade engine on the demo workload."""

from __future__ import annotations

from controlplane.core.types import Action, Axis, PolicyProfile
from controlplane.demo.run_demo import build_engine, sample_requests
from controlplane.pnl import PnlLedger
from controlplane.recorder import JsonlRecorder


def _run_all():
    policy = PolicyProfile(id="test")
    engine = build_engine(policy)
    ledger = PnlLedger()
    recorder = JsonlRecorder()
    by_id = {}
    for ctx in sample_requests():
        result = engine.run(ctx)
        pnl = ledger.book(ctx, result)
        recorder.record(result, pnl, policy_id=policy.id)
        by_id[ctx.request_id] = result
    return by_id, ledger, recorder


def test_pii_leak_is_blocked():
    by_id, _, _ = _run_all()
    assert by_id["req-C"].action == Action.BLOCK
    assert by_id["req-C"].per_axis[Axis.RESPONSIBILITY].p_fail > 0.85


def test_clean_request_passes_and_skips_inapplicable_check():
    by_id, _, _ = _run_all()
    result = by_id["req-A"]
    assert result.action == Action.PASS
    # With no extra samples, self-consistency is not applicable, so the engine never pays for it.
    steps = [s for s in result.trace if s.detector == "self_consistency"]
    assert steps and all(not s.ran and s.reason == "not_applicable" for s in steps)


def test_confident_hallucination_skips_costly_check_on_value():
    by_id, _, _ = _run_all()
    result = by_id["req-B"]
    assert result.action == Action.ESCALATE
    # The cheap signals already put p_fail near certainty, so the T1 check is not worth its cost:
    # the skip is a value-of-information decision, not an applicability one.
    steps = [s for s in result.trace if s.detector == "self_consistency"]
    assert steps and all(not s.ran and s.reason == "voi_below_check_cost" for s in steps)


def test_uncertain_request_runs_the_t1_check():
    by_id, _, _ = _run_all()
    result = by_id["req-E"]
    t1_steps = [s for s in result.trace if s.detector == "self_consistency"]
    assert t1_steps and any(s.ran for s in t1_steps)


def test_workload_is_self_funding():
    _, ledger, _ = _run_all()
    totals = ledger.totals()
    # Route-down and cache savings should exceed what the safety checks spent.
    assert totals.net_usd < 0.0


def test_hash_chain_verifies_and_detects_tampering():
    _, _, recorder = _run_all()
    assert recorder.verify_chain() is True
    # Tamper with a past receipt: the chain must no longer verify.
    recorder.receipts[0].action = Action.PASS
    recorder.receipts[0].expected_loss_after = 999.0
    assert recorder.verify_chain() is False
