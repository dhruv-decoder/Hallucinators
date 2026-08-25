"""Policy generation: turn a plain-language use-case description into a tuned oversight policy.

The brief's first complexity is that different use cases need different risk tolerance and latency budgets;
a one-size checker fails. Instead of asking an operator to hand-tune the VoI knobs (``cost_fail``,
``cost_mitigate``, ``lambda_latency``, thresholds), they answer a few questions -- what is the use case, how
much traffic, how tight is latency, how sensitive is the data, which geography -- and we generate a tailored
``PolicyProfile`` plus a projection (added latency, escalation rate, projected savings) and a plain-English
rationale for every knob. This is what makes ControlPlane feel like a product configured *for you*.
"""

from controlplane.policy.generator import UseCaseSpec, generate_policy

__all__ = ["UseCaseSpec", "generate_policy"]
