"""Abstract detector interfaces -- the third frozen contract.

Two kinds of detector:

- ``Detector`` assesses a *failure-type* axis (performance or responsibility) and returns a ``Signal``
  with a risk score in [0, 1]. These feed the VoI stopping rule.
- ``CostDetector`` assesses the *cost* axis and returns a ``CostOpportunity`` describing a cheaper path
  to the same quality. These feed the P&L ledger's "cost saved" side.

Every detector declares the cost and latency the engine should *expect* before running it, plus an
``informativeness`` prior. Informativeness is the fraction of the remaining uncertainty the detector is
expected to resolve; it is what makes a heavy T2 judge worth more, in the VoI math, than a T0 heuristic.
These are priors we can later learn from the flight recorder.
"""

from __future__ import annotations

import abc
import time

from controlplane.core.types import Axis, CostOpportunity, RequestContext, Signal, Tier


class Detector(abc.ABC):
    """Base class for failure-type (performance / responsibility) detectors."""

    #: Stable identifier used in signals, traces, and receipts.
    name: str = "detector"
    #: Which coupled risk this detector reads.
    axis: Axis
    #: Which cost/latency tier this detector belongs to.
    tier: Tier = Tier.T0
    #: Expected marginal dollar cost of running this detector once.
    est_cost_usd: float = 0.0
    #: Expected added latency (ms) of running this detector once.
    est_latency_ms: float = 1.0
    #: Prior on how much of the remaining uncertainty this detector resolves, in [0, 1].
    informativeness: float = 0.5

    def applicable(self, ctx: RequestContext) -> bool:
        """Whether this detector can assess the request at all.

        A groundedness detector with no retrieved context, or a self-consistency detector with no extra
        samples, is not applicable. The engine skips inapplicable detectors *before* weighing their value
        of information, so it never pays for -- or fabricates -- a check that has nothing to work with.
        Defaults to always applicable.
        """
        return True

    @abc.abstractmethod
    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        """Return ``(risk_score, detail)`` for the request.

        ``risk_score`` is in [0, 1]; higher means the response is more likely a failure on this axis.
        ``detail`` is any structured evidence worth putting in the receipt. Subclasses implement this;
        ``run`` wraps it with timing and packaging so subclasses never have to.
        """

    def run(self, ctx: RequestContext) -> Signal:
        """Run the detector and package the result as a timed ``Signal``."""
        start = time.perf_counter()
        score, detail = self.assess(ctx)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return Signal(
            name=self.name,
            axis=self.axis,
            tier=self.tier,
            score=_clamp01(score),
            cost_usd=self.est_cost_usd,
            latency_ms=max(elapsed_ms, self.est_latency_ms),
            detail=detail,
        )


class CostDetector(abc.ABC):
    """Base class for cost-axis detectors (the funding side of oversight)."""

    name: str = "cost_detector"
    tier: Tier = Tier.T0
    est_cost_usd: float = 0.0
    est_latency_ms: float = 1.0

    @abc.abstractmethod
    def assess(self, ctx: RequestContext) -> CostOpportunity:
        """Return a ``CostOpportunity`` describing any cheaper path to the same quality."""

    def run(self, ctx: RequestContext) -> CostOpportunity:
        """Run the cost detector and stamp it with timing."""
        start = time.perf_counter()
        opp = self.assess(ctx)
        opp.latency_ms = max((time.perf_counter() - start) * 1000.0, self.est_latency_ms)
        opp.cost_usd = self.est_cost_usd
        return opp


def _clamp01(x: float) -> float:
    """Clamp a value into [0, 1]. Detectors should already be in range; this guards against drift."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x
