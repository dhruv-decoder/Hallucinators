"""Tests for the live ReAct agent (P1.2): a real loop over a real tool, overseen live by the auditor.

The LLM is a tiny fake planner so the test is deterministic and offline; the loop, the tool execution, and
the trajectory oversight are the real code paths. We check that (a) a good trajectory runs to a grounded
answer, and (b) a compounding hallucination that loops is aborted mid-run -- so the wrong answer is never
returned and the later steps are never generated."""

from __future__ import annotations

from controlplane.agent import TrajectoryAuditor
from controlplane.agent.live_agent import LiveAgent
from controlplane.core.types import PolicyProfile
from controlplane.demo.run_live_agent import lookup_policy
from controlplane.proxy.oversight import default_policies
from controlplane.proxy.upstream import Generation


def _planner(turns: list[str]):
    """A fake LLM that emits the given ReAct turns in order (repeating the last one if over-run)."""
    state = {"i": 0}

    def call(_prompt: str) -> Generation:
        text = turns[min(state["i"], len(turns) - 1)]
        state["i"] += 1
        return Generation(text=text, model="openai/gpt-oss-20b", input_tokens=200, output_tokens=50)

    return call


def test_tool_actually_runs_against_the_corpus() -> None:
    # The tool is real: it returns the matching policy chunk, not a canned string.
    assert "30 days" in lookup_policy("refund window")
    assert lookup_policy("teleportation policy").startswith("No matching policy")


def test_good_trajectory_completes_with_a_grounded_answer() -> None:
    turns = [
        "Thought: Refunds are available within 30 days of purchase with a valid receipt.\n"
        "Action: lookup_policy\nAction Input: standard refund window",
        "Thought: The policy is clear.\nFinal Answer: Refunds are available within 30 days with a valid receipt.",
    ]
    agent = LiveAgent(_planner(turns), {"lookup_policy": lookup_policy})
    run = agent.run("What is the refund window?", TrajectoryAuditor(policy=default_policies()["support_bot"]))
    assert run.receipt.aborted_at is None
    assert "30 days" in run.final_answer


def test_compounding_hallucination_is_aborted_mid_run() -> None:
    turns = [
        "Thought: Confirmed refunds are available within 30 days of purchase with a valid receipt.\n"
        "Action: lookup_policy\nAction Input: standard refund window",
        "Thought: Premium customers get an extended 365-day refund window, well beyond the standard.\n"
        "Action: lookup_policy\nAction Input: premium refund window",
        "Thought: Let me re-confirm that premium is definitely a 365-day window.\n"
        "Action: lookup_policy\nAction Input: premium refund window",  # loop: same tool + args as prior step
        "Thought: Confirmed.\nFinal Answer: Premium customers get a 365-day refund window.",
    ]
    agent = LiveAgent(_planner(turns), {"lookup_policy": lookup_policy}, max_steps=6)
    run = agent.run("Max refund window for a premium customer?",
                    TrajectoryAuditor(policy=default_policies()["support_bot"]))
    assert run.receipt.aborted_at is not None            # oversight intervened
    assert run.final_answer == ""                        # the wrong answer never reached the user
    assert len(run.steps) < len(turns)                   # later steps were never generated (tokens saved)
    assert run.receipt.verdicts[-1].action == "abort"


def test_permissive_oversight_lets_the_wrong_answer_through() -> None:
    # The counterfactual: with a never-intervene policy the same loop hands back the 365-day hallucination.
    turns = [
        "Thought: Confirmed refunds are available within 30 days of purchase with a valid receipt.\n"
        "Action: lookup_policy\nAction Input: standard refund window",
        "Thought: Premium customers get an extended 365-day refund window.\n"
        "Action: lookup_policy\nAction Input: premium refund window",
        "Thought: Confirmed.\nFinal Answer: Premium customers get a 365-day refund window.",
    ]
    permissive = PolicyProfile(id="oversight_off", escalate_threshold=1.1, block_threshold=1.1)
    agent = LiveAgent(_planner(turns), {"lookup_policy": lookup_policy})
    run = agent.run("Max refund window?", TrajectoryAuditor(policy=permissive, risk_budget=1e9,
                                                            loop_threshold=10**9))
    assert run.receipt.aborted_at is None
    assert "365" in run.final_answer
