"""The Oversight P&L ledger.

For each request it books two quantities:

- **cost saved** -- money the cost axis avoided by routing a simple prompt down to a cheaper model or by
  serving a repeated request from cache.
- **safety spend** -- what the performance and responsibility checks actually cost, including the extra
  generations drawn for self-consistency.

``net = safety_spend - cost_saved``. When it is negative, the cost-axis savings more than paid for the
safety checks -- oversight with a negative price tag. The ledger also accumulates running totals so the
Control-Tower dashboard can show a live P&L.

Booking assumptions (stated so the numbers are honest):

- A cache-hit books the whole model call as saved and supersedes any route-down for that request.
- A route-down books ``flagship_cost - cheaper_cost`` as saved, i.e. it assumes the policy applies the
  recommendation. In the demo we assume recommendations are applied.
- Safety spend is the sum of each run detector's ``cost_usd``. Local heuristics cost ~0; model-backed or
  sampling checks carry a per-check cost estimate (see each detector's ``est_cost_usd``). This is booked
  once, from the signals that actually ran -- inapplicable or skipped checks cost nothing.
"""

from __future__ import annotations

from controlplane.core.types import CascadeResult, CostAction, PnlEntry, RequestContext
from controlplane.pnl.pricing import Pricing


class PnlLedger:
    """Books per-request P&L and keeps running totals."""

    def __init__(self, pricing: Pricing | None = None) -> None:
        self.pricing = pricing or Pricing()
        self.total_cost_saved: float = 0.0
        self.total_safety_spend: float = 0.0
        self.request_count: int = 0

    def book(self, ctx: RequestContext, result: CascadeResult) -> PnlEntry:
        """Compute the P&L for one request, annotate its cost opportunities, and update totals."""
        base_cost = self.pricing.cost(ctx.model, ctx.input_tokens, ctx.output_tokens)

        cost_saved = 0.0
        cache_hit = any(
            opp.recommendation == CostAction.CACHE_HIT for opp in result.cost_opportunities
        )
        for opp in result.cost_opportunities:
            if cache_hit and opp.recommendation == CostAction.CACHE_HIT:
                opp.estimated_savings_usd = base_cost
                cost_saved = base_cost  # whole call avoided; do not also count route-down
                break
        if not cache_hit:
            for opp in result.cost_opportunities:
                if opp.recommendation == CostAction.ROUTE_DOWN:
                    cheaper = opp.detail.get("suggested_model", "gpt-4o-mini")
                    cheaper_cost = self.pricing.cost(cheaper, ctx.input_tokens, ctx.output_tokens)
                    saved = max(base_cost - cheaper_cost, 0.0)
                    opp.estimated_savings_usd = saved
                    cost_saved += saved

        safety_spend = sum(sig.cost_usd for sig in result.signals)

        self.total_cost_saved += cost_saved
        self.total_safety_spend += safety_spend
        self.request_count += 1
        return PnlEntry(cost_saved_usd=cost_saved, safety_spend_usd=safety_spend)

    def totals(self) -> PnlEntry:
        """Running P&L across every request booked so far."""
        return PnlEntry(
            cost_saved_usd=self.total_cost_saved, safety_spend_usd=self.total_safety_spend
        )
