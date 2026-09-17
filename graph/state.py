"""Shared state schema for the multi-agent code system's LangGraph."""
from __future__ import annotations

from typing import TypedDict, Literal


class CritiqueRound(TypedDict):
    round_number: int
    code_snapshot: str
    reviewer_feedback: str
    verdict: Literal["approve", "revise"]


class TestResult(TypedDict):
    passed: bool
    stdout: str
    stderr: str
    exit_code: int


class AgentState(TypedDict, total=False):
    # Task definition
    task: str

    # Planner output
    plan: str

    # Coder output (current working code)
    code: str

    # Tester output
    test_result: TestResult

    # Reviewer output
    review_verdict: Literal["approve", "revise"]
    review_feedback: str

    # Debate/critique loop bookkeeping (inner loop, Coder <-> Reviewer)
    critique_round: int
    critique_max_rounds: int
    critique_history: list[CritiqueRound]

    # Supervisor bookkeeping (outer loop)
    supervisor_step: int
    supervisor_max_steps: int
    next_agent: str

    # Human-in-the-loop
    human_decision: Literal["approve", "reject"]
    human_feedback: str

    # Trace / observability
    trace: list[dict]
