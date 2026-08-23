"""Agentic trajectory oversight -- the VoI cascade extended from one call to a whole agent run.

A tool-calling agent takes many steps, and one bad step shapes every step after it: an early hallucination
gets treated as fact, the agent loops trying to reconcile it, and tokens (and trust) burn. The brief calls
this out as its hardest complexity (multi-turn / agents compound risk).

ControlPlane treats **an agent step as just another monitored call** -- the same three-axis cascade runs on
each step -- and adds *trajectory-level* signals that only make sense across steps: compounding risk, loops,
and tool-call waste. Following the 2026 runtime-guardrail consensus, it checks **before / during / after**
each step and aborts on the *unrecoverable* compounding failure rather than the first blip. Aborting early is
also the agent "waste-killer": the steps we never run are money saved.
"""

from controlplane.agent.auditor import TrajectoryAuditor
from controlplane.agent.types import AgentStep, StepVerdict, TrajectoryReceipt

__all__ = ["TrajectoryAuditor", "AgentStep", "StepVerdict", "TrajectoryReceipt"]
