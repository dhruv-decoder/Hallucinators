"""The value-of-information (VoI) decision core.

This module is the intellectual centre of ControlPlane. It answers one question for every response and
every axis: *is it worth running the next, more expensive check?* The answer is an economic one -- run a
check only when the expected reduction in loss it buys exceeds what the check itself costs in dollars and
latency.

Derivation
----------
For a failure-type axis, let:

- ``p``  = calibrated probability the response is a failure on this axis, in [0, 1].
- ``C``  = ``cost_fail``: the business cost if such a failure reaches the user.
- ``m``  = ``cost_mitigate``: the cost of the mitigating action (escalate / block / repair) -- human
  time, user friction, added latency.

**Best action given current belief (no more information).** We either pass (expected loss ``p*C``) or
mitigate (cost ``m``). A rational controller takes the cheaper of the two::

    bayes_risk(p, C, m) = min(p * C, m)

**Value of a check.** A *perfectly informative* check reveals the true state. Then with probability ``p``
the response really is a failure and we mitigate at cost ``min(m, C)``; with probability ``1 - p`` it is
fine and we pass at cost 0. So the residual loss after a perfect check is::

    residual_after_perfect(p, C, m) = p * min(m, C)

A real check only resolves a fraction ``eta`` (``informativeness``) of the uncertainty, so::

    VoI = eta * ( bayes_risk(p, C, m) - residual_after_perfect(p, C, m) )
        = eta * ( min(p*C, m) - p*min(m, C) )

This is always non-negative (see the tests), and it captures both failure modes cleanly:

- If we would otherwise **pass** (``p*C <= m``), the reduction is ``eta * p * (C - m)`` -- the check earns
  its keep by catching the ``p``-fraction of real failures and mitigating them cheaply instead of eating
  ``C``. This is the under-flagging (missed failure) saving.
- If we would otherwise **mitigate** (``p*C > m``), the reduction is ``eta * m * (1 - p)`` -- the check
  earns its keep by clearing the ``(1 - p)``-fraction of false alarms and avoiding needless mitigation.
  This is the over-flagging (alert-fatigue) saving.

**Stopping rule.** Run the next check iff ``VoI > check_cost``, where
``check_cost = cost_usd + lambda_latency * latency_ms``. ``C``, ``m``, and ``lambda_latency`` all come
from the active policy profile, so a single set of per-use-case knobs tunes the entire
over-flag / under-flag / latency trade-off -- rather than hand-tuning each detector.
"""

from __future__ import annotations

from dataclasses import dataclass


def expected_loss(p_fail: float, cost_fail: float) -> float:
    """Expected loss of forwarding a response unchecked: ``P(failure) * Cost(failure)``."""
    return p_fail * cost_fail


def bayes_risk(p_fail: float, cost_fail: float, cost_mitigate: float) -> float:
    """Residual loss under the best action given current belief, with no further information.

    Either pass (risk ``p_fail * cost_fail``) or mitigate (cost ``cost_mitigate``); take the cheaper.
    """
    return min(p_fail * cost_fail, cost_mitigate)


def residual_after_perfect(p_fail: float, cost_fail: float, cost_mitigate: float) -> float:
    """Expected loss if the axis could be perfectly resolved and then acted on optimally.

    With probability ``p_fail`` it is a true failure and we mitigate at cost ``min(cost_mitigate,
    cost_fail)`` (we would never spend more mitigating than the failure itself costs); otherwise 0.
    """
    return p_fail * min(cost_mitigate, cost_fail)


def value_of_information(
    p_fail: float,
    cost_fail: float,
    cost_mitigate: float,
    informativeness: float,
) -> float:
    """Expected reduction in loss from running a check that resolves a fraction ``informativeness``
    of the remaining uncertainty on this axis. Always non-negative."""
    perfect_gain = bayes_risk(p_fail, cost_fail, cost_mitigate) - residual_after_perfect(
        p_fail, cost_fail, cost_mitigate
    )
    return informativeness * perfect_gain


def check_cost(cost_usd: float, latency_ms: float, lambda_latency: float) -> float:
    """Total cost of a check: its dollar cost plus its latency priced at ``lambda_latency`` ($/ms)."""
    return cost_usd + lambda_latency * latency_ms


@dataclass(frozen=True)
class VoIDecision:
    """The result of weighing one candidate check: what it is worth, what it costs, and whether to run."""

    voi: float
    cost: float
    run: bool
    reason: str


def decide_check(
    p_fail: float,
    cost_fail: float,
    cost_mitigate: float,
    informativeness: float,
    detector_cost_usd: float,
    detector_latency_ms: float,
    lambda_latency: float,
) -> VoIDecision:
    """Apply the stopping rule to a single candidate check.

    Runs the check iff its value of information strictly exceeds its total (dollar + latency) cost.
    """
    voi = value_of_information(p_fail, cost_fail, cost_mitigate, informativeness)
    cost = check_cost(detector_cost_usd, detector_latency_ms, lambda_latency)
    run = voi > cost
    if run:
        reason = "voi_exceeds_check_cost"
    else:
        reason = "voi_below_check_cost"
    return VoIDecision(voi=voi, cost=cost, run=run, reason=reason)


def combine_probabilities(probs: list[float], strategy: str = "noisy_or") -> float:
    """Combine several detectors' calibrated failure probabilities on one axis into a single estimate.

    - ``noisy_or`` (default): ``1 - prod(1 - p_i)`` -- the probability that at least one detector is
      right that this is a failure. Interpretable and monotone, but can over-inflate with many weak,
      correlated detectors; the combined score can itself be re-calibrated on held-out data.
    - ``max``: the single most alarming detector governs. Conservative and simple.
    - ``mean``: the average. Smooths noise but dilutes a strong lone signal.

    An empty list yields 0.0 (no evidence of failure).
    """
    if not probs:
        return 0.0
    if strategy == "max":
        return max(probs)
    if strategy == "mean":
        return sum(probs) / len(probs)
    if strategy == "noisy_or":
        product = 1.0
        for p in probs:
            product *= 1.0 - p
        return 1.0 - product
    raise ValueError(f"unknown combine strategy: {strategy!r}")
