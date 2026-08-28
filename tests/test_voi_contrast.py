"""Tests for the VoI skip-vs-buy contrast (the adaptive-oversight centerpiece).

Same engine, same detectors, same policy: a safe response must SKIP the expensive check while an uncertain
one must BUY it. This is deterministic and offline (heuristics; the bought check is self-consistency), so it
is a reliable regression guard for the core claim.
"""

from __future__ import annotations

from controlplane.cascade.voi_contrast import voi_contrast


def test_safe_response_skips_and_uncertain_buys() -> None:
    data = voi_contrast()
    assert data["safe"]["bought_a_check"] is False
    assert data["uncertain"]["bought_a_check"] is True


def test_bought_check_only_when_voi_exceeds_cost() -> None:
    data = voi_contrast()
    # The safe case leaves (almost) no uncertainty after the cheap checks -> VoI below the check cost.
    safe_checks = data["safe"]["expensive_checks"]
    assert safe_checks and all(c["voi"] <= c["check_cost"] for c in safe_checks if not c["ran"])
    # The uncertain case has at least one check whose VoI exceeds its cost and therefore ran.
    unc_checks = data["uncertain"]["expensive_checks"]
    assert any(c["ran"] and c["voi"] > c["check_cost"] for c in unc_checks)


def test_uncertain_case_escalates_to_a_human() -> None:
    # Buying the check surfaces the disagreement, so the uncertain response is not silently passed.
    data = voi_contrast()
    assert data["uncertain"]["action"] in ("escalate", "block", "annotate")
    assert data["safe"]["action"] == "pass"
