"""Model pricing used to compute the Oversight P&L.

IMPORTANT: the numbers below are ILLUSTRATIVE, order-of-magnitude placeholders so the demo produces a
concrete P&L. They are not verified provider prices. Before any figure is shown in a slide, README, or
video, replace these with values sourced in docs/EVIDENCE.md (per AI_CODING_GUIDELINES.md section 3).
Prices are per 1,000 tokens, as (input_price, output_price), in USD.
"""

from __future__ import annotations


class Pricing:
    """Look up model call costs and provide the default cheaper model for route-down."""

    #: Illustrative placeholder prices (input, output) per 1k tokens. Replace with sourced values.
    DEFAULT_PRICES: dict[str, tuple[float, float]] = {
        "gpt-4o": (0.005, 0.015),
        "gpt-4o-mini": (0.00015, 0.0006),
        "local": (0.0, 0.0),
    }

    def __init__(self, prices: dict[str, tuple[float, float]] | None = None) -> None:
        self.prices = dict(prices) if prices is not None else dict(self.DEFAULT_PRICES)

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Cost in USD of a single call. Unknown models fall back to the flagship rate (conservative)."""
        in_price, out_price = self.prices.get(model, self.prices.get("gpt-4o", (0.005, 0.015)))
        return (input_tokens / 1000.0) * in_price + (output_tokens / 1000.0) * out_price
