"""Model pricing used to compute the Oversight P&L.

Prices are per 1,000 tokens, as ``(input_price, output_price)`` in USD, sourced from public provider pricing
as of **August 2026**. They are list prices, not negotiated
enterprise rates, and they move often -- treat the P&L as an order-of-magnitude, reproducible estimate, not a
billing statement. The route-down savings the ledger books come straight from the flagship-vs-cheaper gap
below, so they track real provider economics.
"""

from __future__ import annotations


class Pricing:
    """Look up model call costs and provide the default cheaper model for route-down."""

    #: Cost of one human-in-the-loop review, booked when a request is escalated. This is an enterprise
    #: assumption (analyst time), not a provider price: roughly two minutes of a reviewer at a loaded
    #: ~$45/hr rate. It exists so the risk/cost tradeoff is expressed in real dollars -- a stricter
    #: appetite escalates more and therefore costs more human time. Tune per organisation.
    HUMAN_REVIEW_USD: float = 1.50

    #: (input, output) USD per 1k tokens. Sourced Aug 2026.
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
        # Groq (OpenAI-compatible, used by the live Playground). Approximate provider list prices -- verify
        # before quoting. The free tier bills $0; these list rates are what a paying
        # deployment would pay, so the P&L reflects real economics rather than $0.
        "openai/gpt-oss-120b": (0.00015, 0.00060),
        "openai/gpt-oss-20b": (0.00005, 0.00020),
        "qwen/qwen3.6-27b": (0.00020, 0.00060),
        "groq/compound": (0.00015, 0.00060),
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

    def review_cost(self, escalations: int) -> float:
        """Human-review spend for ``escalations`` requests sent to a person (analyst time)."""
        return max(escalations, 0) * self.HUMAN_REVIEW_USD
