"""Tests for the Oversight P&L ledger."""

from __future__ import annotations

from controlplane.core.types import (
    Axis,
    CascadeResult,
    CostAction,
    CostOpportunity,
    RequestContext,
    Signal,
    Tier,
)
from controlplane.pnl import PnlLedger


def _ctx(model="gpt-4o", samples=None):
    return RequestContext(
        request_id="r", model=model, input_tokens=1000, output_tokens=1000, samples=samples or []
    )


def test_route_down_books_savings():
    ledger = PnlLedger()
    result = CascadeResult(request_id="r", use_case="u")
    result.cost_opportunities.append(
        CostOpportunity(
            name="model_overkill",
            tier=Tier.T0,
            recommendation=CostAction.ROUTE_DOWN,
            detail={"suggested_model": "gpt-4o-mini"},
        )
    )
    pnl = ledger.book(_ctx(), result)
    # gpt-4o costs more than gpt-4o-mini, so we saved the difference and spent nothing on safety.
    assert pnl.cost_saved_usd > 0.0
    assert pnl.safety_spend_usd == 0.0
    assert pnl.net_usd < 0.0


def test_cache_hit_supersedes_route_down():
    ledger = PnlLedger()
    result = CascadeResult(request_id="r", use_case="u")
    result.cost_opportunities.append(
        CostOpportunity(name="semantic_cache", tier=Tier.T0, recommendation=CostAction.CACHE_HIT)
    )
    result.cost_opportunities.append(
        CostOpportunity(
            name="model_overkill",
            tier=Tier.T0,
            recommendation=CostAction.ROUTE_DOWN,
            detail={"suggested_model": "gpt-4o-mini"},
        )
    )
    pnl = ledger.book(_ctx(), result)
    # A cache hit avoids the whole call, so savings equal the full flagship cost.
    full = ledger.pricing.cost("gpt-4o", 1000, 1000)
    assert abs(pnl.cost_saved_usd - full) < 1e-12


def test_safety_spend_sums_run_detector_costs():
    ledger = PnlLedger()
    result = CascadeResult(request_id="r", use_case="u")
    # A model-backed / sampling check that actually ran carries a per-check cost.
    result.signals.append(
        Signal(name="self_consistency", axis=Axis.PERFORMANCE, tier=Tier.T1, score=0.5, cost_usd=0.002)
    )
    # A free heuristic contributes nothing to safety spend.
    result.signals.append(
        Signal(name="overconfidence", axis=Axis.PERFORMANCE, tier=Tier.T0, score=0.1, cost_usd=0.0)
    )
    pnl = ledger.book(_ctx(), result)
    assert abs(pnl.safety_spend_usd - 0.002) < 1e-12
