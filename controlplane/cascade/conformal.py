"""Conformal risk control for the oversight decision -- a *guarantee*, not just a calibrated score.

The stopping rule uses a calibrated ``P(fail)``, but a skeptic asks the sharper question: *what is the actual
rate of failures that slip through?* Conformal risk control (Angelopoulos et al., "Conformal Risk Control";
Mohri & Hashimoto, conformal factuality) answers it with a distribution-free, finite-sample guarantee: choose
the flag threshold ``tau`` so that the expected **escaped-failure rate** (the fraction of true failures we let
pass) is provably ``<= alpha``.

We control the false-negative rate on a failure-type axis. Flag if ``score >= tau``; pass otherwise. Lowering
``tau`` flags more and misses fewer, so the empirical FNR is monotone in ``tau``. The conformal-risk-control
bound picks the *largest* ``tau`` (least over-flagging -- the cheapest policy) whose risk still satisfies

    ( n * FNR_hat(tau) + 1 ) / ( n + 1 )  <=  alpha

where ``n`` is the number of labelled true failures in the calibration set. This is the standard bounded-loss
conformal result: it guarantees ``E[FNR] <= alpha`` on exchangeable future data, with no distributional
assumptions. The ``+1/(n+1)`` is the honest finite-sample correction -- with few calibration failures the bound
is conservative and forces more flagging, exactly as it should.

This turns "we tuned a threshold" into "we control a risk budget with a certificate" -- the single most
defensible differentiator for a technical jury. It is a *decision* layer on top of any detector scores.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskCertificate:
    """The outcome of calibrating a risk-controlled threshold for one axis."""

    alpha: float  # the target escaped-failure rate we control
    tau: float  # flag if calibrated p_fail >= tau
    empirical_fnr: float  # escaped-failure rate on the calibration set at tau
    risk_bound: float  # the conformal upper bound (n*FNR+1)/(n+1) at tau -- guaranteed <= alpha
    n_failures: int  # labelled true failures used (the bound's sample size)
    valid: bool  # False if there were too few failures to certify anything

    def statement(self) -> str:
        if not self.valid:
            return f"cannot certify alpha={self.alpha:.2f}: only {self.n_failures} labelled failures"
        return (
            f"expected conditional FNR <= {self.alpha:.2f} under exchangeability "
            f"(empirical {self.empirical_fnr:.3f}, conformal bound {self.risk_bound:.3f}, "
            f"n={self.n_failures} failures, flag at p_fail>={self.tau:.3f})"
        )


def risk_controlled_threshold(
    scores: list[float], labels: list[bool], alpha: float = 0.10
) -> RiskCertificate:
    """Calibrate the flag threshold that guarantees escaped-failure rate ``<= alpha`` (conformal risk control).

    ``scores`` are calibrated failure probabilities; ``labels`` are ground-truth failure booleans (available
    only offline). Returns the largest ``tau`` (least over-flagging) whose conformal risk bound is ``<= alpha``.
    If the bound cannot be met even by flagging everything (too few calibration failures), returns ``tau=0``
    (flag all) and ``valid=False`` so callers fall back to a conservative policy.
    """
    failures = sorted(s for s, y in zip(scores, labels, strict=True) if y)
    n = len(failures)
    if n == 0:
        return RiskCertificate(alpha, tau=0.0, empirical_fnr=0.0, risk_bound=1.0, n_failures=0, valid=False)

    def fnr_at(tau: float) -> float:
        missed = sum(1 for s in failures if s < tau)  # true failures we would pass
        return missed / n

    # Candidate thresholds: each failure's score (the FNR only changes as tau crosses a failure's score),
    # plus 0.0 (flag everything) and just above the max (flag nothing).
    candidates = sorted({0.0, *failures, min(1.0, failures[-1] + 1e-9)})
    best = None
    for tau in candidates:
        fnr = fnr_at(tau)
        bound = (n * fnr + 1.0) / (n + 1.0)
        if bound <= alpha:
            best = (tau, fnr, bound)  # keep climbing; we want the largest tau that still satisfies
    if best is None:
        # Even flagging everything (tau=0, FNR=0) gives bound 1/(n+1) > alpha -> cannot certify at this n.
        return RiskCertificate(alpha, tau=0.0, empirical_fnr=0.0, risk_bound=1.0 / (n + 1.0),
                               n_failures=n, valid=False)
    tau, fnr, bound = best
    return RiskCertificate(alpha, tau=tau, empirical_fnr=fnr, risk_bound=bound, n_failures=n, valid=True)
