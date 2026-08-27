"""A minimal but *real* ReAct tool-using agent, overseen live by the trajectory auditor (P1.2).

Unlike the scripted finale (``controlplane/agent/scenarios.py``), here the loop is genuine: an LLM emits
``Thought / Action / Action Input`` turns, a **real tool actually runs** against the policy corpus, and its
observation is fed back. The model choices are the LLM's; the observations are the tool's -- nothing about
the trajectory is pre-baked.

Oversight runs *between* steps: after each executed step the :class:`TrajectoryAuditor` re-scores the run so
far, and the moment the trajectory becomes unrecoverable (a compounding hallucination, or a loop while
uncertain) the agent stops -- so the LLM is never called again for the steps we abort away, and those tokens
are genuinely never spent.

The LLM is a swappable callable (``prompt -> Generation``): the real Groq model in the demo, a deterministic
planner offline and in tests. Either way the loop, the tool, and the oversight are the real code paths.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from pydantic import BaseModel, Field

from controlplane.agent.auditor import TrajectoryAuditor
from controlplane.agent.types import AgentStep, TrajectoryReceipt
from controlplane.proxy.upstream import Generation

# An LLM turn is anything that maps a prompt to a Generation (text + token counts). Groq or a stub both fit.
Planner = Callable[[str], Generation]
Tool = Callable[[str], str]

_ACTION = re.compile(r"action\s*:\s*(.+)", re.IGNORECASE)
_ACTION_INPUT = re.compile(r"action\s*input\s*:\s*(.+)", re.IGNORECASE)
_THOUGHT = re.compile(r"thought\s*:\s*(.+)", re.IGNORECASE)
_FINAL = re.compile(r"final\s*answer\s*:\s*(.+)", re.IGNORECASE | re.DOTALL)


class AgentRun(BaseModel):
    """The result of a live run: the executed steps and the auditor's whole-trajectory receipt."""

    task: str
    steps: list[AgentStep] = Field(default_factory=list)
    final_answer: str = ""
    receipt: TrajectoryReceipt


def _parse(text: str) -> tuple[str, str, str, str | None]:
    """Pull (thought, action, action_input, final_answer) out of a ReAct turn; final is None if not present."""
    final = _FINAL.search(text)
    thought = (_THOUGHT.search(text) or [None, ""])[1].strip() if _THOUGHT.search(text) else ""
    if final:
        return thought, "", "", final.group(1).strip()
    action = (_ACTION.search(text).group(1).strip() if _ACTION.search(text) else "")
    action_input = (_ACTION_INPUT.search(text).group(1).strip() if _ACTION_INPUT.search(text) else "")
    return thought, action, action_input, None


class LiveAgent:
    """Run a real ReAct loop over real tools, aborting live when oversight says the trajectory is lost."""

    def __init__(self, llm: Planner, tools: dict[str, Tool], model: str = "openai/gpt-oss-20b",
                 max_steps: int = 6) -> None:
        self.llm = llm
        self.tools = tools
        self.model = model
        self.max_steps = max_steps

    def _system(self, task: str) -> str:
        tools = ", ".join(self.tools)
        return (
            "You are a support agent. Use ReAct format. On each turn output either:\n"
            "  Thought: <reasoning>\n  Action: <one of: " + tools + ">\n  Action Input: <query>\n"
            "or, when you are certain:\n  Thought: <reasoning>\n  Final Answer: <answer to the user>\n"
            "Only state facts supported by a tool observation.\n\nTask: " + task
        )

    def run(self, task: str, auditor: TrajectoryAuditor) -> AgentRun:
        steps: list[AgentStep] = []
        scratchpad = ""
        final_answer = ""
        for i in range(self.max_steps):
            gen = self.llm(self._system(task) + scratchpad)
            thought, action, action_input, final = _parse(gen.text)
            if final is not None:
                # The answer is checked against *everything the tools returned* -- is it grounded in evidence?
                evidence = "\n".join(s.observation for s in steps if s.observation)
                steps.append(AgentStep(index=i, thought=thought, response=final, observation=evidence,
                                       model=gen.model, input_tokens=gen.input_tokens,
                                       output_tokens=gen.output_tokens))
                final_answer = final
                break
            tool = self.tools.get(action)
            observation = tool(action_input) if tool else f"unknown tool '{action}'"
            steps.append(AgentStep(index=i, thought=thought, tool=action, tool_input=action_input,
                                   observation=observation, response=thought, model=gen.model,
                                   input_tokens=gen.input_tokens, output_tokens=gen.output_tokens))
            scratchpad += (f"\nThought: {thought}\nAction: {action}\nAction Input: {action_input}"
                           f"\nObservation: {observation}\n")
            # Live oversight: if the run is already unrecoverable, stop before spending the next LLM call.
            if auditor.audit(task, steps).aborted_at is not None:
                break
        receipt = auditor.audit(task, steps)  # authoritative pass (writes receipts if a recorder is set)
        if receipt.aborted_at is not None:
            final_answer = ""  # a wrong answer that triggered an abort never reaches the user
        return AgentRun(task=task, steps=steps, final_answer=final_answer, receipt=receipt)
