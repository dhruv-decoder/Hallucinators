"""The Adaptive Oversight Thermostat.

A feedback controller that adjusts how thorough oversight is, in response to how risky recent traffic
has been. It outputs a *scrutiny* multiplier that the VoI stopping rule applies (see
``voi.decide_check``): above 1.0 the system buys more checks, below 1.0 it relaxes so the safe majority
is not slowed.

It is a simple proportional controller over a sliding window of observed risk::

    scrutiny = clip( 1 + gain * (recent_mean_risk - setpoint),  s_min,  s_max )

- ``setpoint`` is the level of risk we are willing to tolerate before tightening.
- ``recent_mean_risk`` is the mean, over the last ``window`` requests, of a per-request risk score in
  [0, 1] (we use the maximum calibrated failure probability across axes).
- ``gain`` sets how sharply scrutiny reacts.

Causality: the scrutiny for a request is decided from the risk observed on *previous* requests, then that
request is run, then its risk is fed back. So a burst of risky traffic ramps scrutiny up over the next
few requests, and it decays back once the burst passes.

This is intentionally a transparent controller rather than a black box: every input and output is
inspectable, which matters for the audit trail and for explaining it in the AI discussion.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from controlplane.core.types import CascadeResult


def risk_score(result: CascadeResult) -> float:
    """Per-request risk in [0, 1]: the maximum calibrated failure probability across axes."""
    if not result.per_axis:
        return 0.0
    return max(outcome.p_fail for outcome in result.per_axis.values())


@dataclass
class Thermostat:
    """Proportional controller mapping recent observed risk to a scrutiny multiplier."""

    setpoint: float = 0.15
    gain: float = 4.0
    s_min: float = 0.5
    s_max: float = 3.0
    window: int = 5

    def __post_init__(self) -> None:
        self._history: deque[float] = deque(maxlen=self.window)
        self._scrutiny: float = 1.0

    @property
    def scrutiny(self) -> float:
        """The current scrutiny multiplier."""
        return self._scrutiny

    def recommend(self) -> float:
        """Scrutiny to use for the next request, from the risk seen so far. 1.0 until any data arrives."""
        if not self._history:
            self._scrutiny = 1.0
            return self._scrutiny
        recent = sum(self._history) / len(self._history)
        raw = 1.0 + self.gain * (recent - self.setpoint)
        self._scrutiny = min(max(raw, self.s_min), self.s_max)
        return self._scrutiny

    def observe(self, risk: float) -> None:
        """Feed back the risk actually seen on a request."""
        self._history.append(risk)
