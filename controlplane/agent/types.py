"""Contracts for agent-trajectory oversight.

An ``AgentStep`` is one turn of a tool-calling agent (a thought, an optional tool call and its observation,
and the model's text that turn). ``StepVerdict`` is the auditor's read on a step; ``TrajectoryReceipt`` is
the whole-run summary -- including where it aborted and how much waste that avoided.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from controlplane.core.types import Axis


class AgentStep(BaseModel):
    """One turn of a tool-calling agent, everything the per-step and trajectory checks look at."""

    index: int
    thought: str = ""
    tool: str = ""  # tool name called this step; "" for a pure reasoning/answer step
    tool_input: str = ""  # the arguments passed to the tool
    observation: str = ""  # the tool's result, fed back to the model (checked for indirect injection)
    response: str = ""  # the model's text this step (the final answer on the last step)
    model: str = "gpt-4o"
    input_tokens: int = 0
    output_tokens: int = 0

    def signature(self) -> str:
        """Loop key: the same tool called with the same arguments is a repeat (no new information)."""
        return f"{self.tool}({' '.join(self.tool_input.lower().split())})"


class StepVerdict(BaseModel):
    """The auditor's decision on one executed step."""

    index: int
    per_axis_p_fail: dict[Axis, float] = Field(default_factory=dict)
    step_risk: float = 0.0  # max axis p_fail this step
    cumulative_risk: float = 0.0  # running sum of estimated expected loss across the trajectory
    loop_repeat: int = 0  # how many times this step's tool+args signature has now occurred
    wasted: bool = False  # this step produced no new information (a repeat)
    action: str = "continue"  # continue | escalate | abort
    reason: str = ""
    receipt_id: str = ""


class TrajectoryReceipt(BaseModel):
    """The whole-run summary an operator (or the compliance pack) reads."""

    trajectory_id: str
    task: str = ""
    n_steps_planned: int = 0
    n_steps_executed: int = 0
    aborted_at: int | None = None
    final_action: str = "completed"  # completed | escalated | blocked
    cumulative_risk: float = 0.0
    wasted_steps: int = 0
    wasted_usd: float = 0.0  # cost of the planned-but-not-executed steps we saved by aborting
    verdicts: list[StepVerdict] = Field(default_factory=list)
    summary: str = ""
