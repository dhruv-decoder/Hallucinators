"""Replay / What-If: re-run a recorded workload under different oversight policies to compare outcomes."""

from controlplane.replay.simulator import ScenarioResult, WhatIfSimulator

__all__ = ["WhatIfSimulator", "ScenarioResult"]
