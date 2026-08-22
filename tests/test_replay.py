"""Tests for the What-If / Replay simulator."""

from __future__ import annotations

from controlplane.demo.run_demo import build_engine
from controlplane.demo.run_whatif import policies
from controlplane.demo.workload import synthetic_workload
from controlplane.replay import WhatIfSimulator


def _results():
    sim = WhatIfSimulator(synthetic_workload(), build_engine)
    return sim.compare(policies())


def test_oversight_off_is_the_riskiest_and_costs_nothing_to_run():
    r = _results()
    off = r["oversight_off"]
    # Every controlled policy leaves at most as much residual risk as doing nothing.
    for name in ["strict", "balanced", "lenient"]:
        assert r[name].residual_risk <= off.residual_risk + 1e-9
    # Oversight off books no savings and no spend.
    assert off.cost_saved_usd == 0.0 and off.safety_spend_usd == 0.0 and off.net_usd == 0.0


def test_risk_appetite_is_a_monotonic_dial():
    r = _results()
    strict, balanced, lenient = r["strict"], r["balanced"], r["lenient"]
    # Stricter appetite = less residual risk reaching users, but more human escalations. A real dial,
    # not three identical rows: the borderline requests are what make the policies diverge.
    assert strict.residual_risk < balanced.residual_risk < lenient.residual_risk
    assert strict.escalation_rate > balanced.escalation_rate > lenient.escalation_rate


def test_controls_are_self_funding_on_this_workload():
    r = _results()
    assert r["balanced"].net_usd < 0.0


def test_total_risk_is_constant_across_scenarios():
    # Risk appetite (thresholds) varies but the risk model (cost_fail) is held constant, so the
    # estimated total risk is identical -- only what we do about it changes.
    r = _results()
    totals = {s.total_risk for s in r.values()}
    assert max(totals) - min(totals) < 1e-9
