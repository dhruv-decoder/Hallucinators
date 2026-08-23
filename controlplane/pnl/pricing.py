"""Model pricing used to compute the Oversight P&L.

Prices are per 1,000 tokens, as ``(input_price, output_price)`` in USD, sourced from public provider pricing
as of **August 2026** (see ``docs/EVIDENCE.md`` for the links). They are list prices, not negotiated
enterprise rates, and they move often -- treat the P&L as an order-of-magnitude, reproducible estimate, not a
billing statement. The route-down savings the ledger books come straight from the flagship-vs-cheaper gap
below, so they track real provider economics.
"""

from __future__ import annotations


class Pricing:
    """Look up model call costs and provide the default cheaper model for route-down."""

    #: (input, output) USD per 1k tokens. Sourced Aug 2026 -- see docs/EVIDENCE.md.
    DEFAULT_PRICES: dict[str, tuple[float, float]] = {
        # OpenAI
        "gpt-4o": (0.0025, 0.010),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-5": (0.00125, 0.010),
        "gpt-5-mini": (0.00025, 0.002),
        # Anthropic
        "claude-opus-5": (0.005, 0.025),
        "claude-sonnet-5": (0.002, 0.010),
        "claude-haiku-4.5": (0.001, 0.005),
        # Local / open-weights (Ollama / vLLM) and detector models run on our own hardware -> ~0 marginal.
        "local": (0.0, 0.0),
        "ollama": (0.0, 0.0),
    }

    def __init__(self, prices: dict[str, tuple[float, float]] | None = None) -> None:
        self.prices = dict(prices) if prices is not None else dict(self.DEFAULT_PRICES)

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Cost in USD of a single call. Unknown models fall back to the flagship rate (conservative)."""
        in_price, out_price = self.prices.get(model, self.prices.get("gpt-4o", (0.0025, 0.010)))
        return (input_tokens / 1000.0) * in_price + (output_tokens / 1000.0) * out_price
