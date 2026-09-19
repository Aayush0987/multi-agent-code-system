"""The Coder <-> Reviewer debate/critique loop (inner loop, nested inside
the outer supervisor graph built in Phase 4).

Flow: Coder produces code -> Tester runs it -> Reviewer critiques (code +
test result) -> if approved or the round cap is hit, stop; otherwise route
back to the Coder with the Reviewer's feedback for another revision.

The round cap (`critique_max_rounds`) is enforced independently of the outer
supervisor's own iteration limit (Phase 6).
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from agents.coder import write_code
from agents.reviewer import review_code
from agents.tester import run_tests
from graph.state import AgentState
from graph.trace import diff_summary, log_event

DEFAULT_MAX_ROUNDS = 3


def coder_node(state: AgentState) -> dict:
    feedback = state.get("review_feedback")
    previous_code = state.get("code")
    code = write_code(state["plan"], feedback=feedback)

    round_number = state.get("critique_round", 0) + 1
    trace = list(state.get("trace", []))
    trace.append(
        log_event(
            "coder",
            event="revised_code" if previous_code else "wrote_code",
            round=round_number,
            reason=feedback or "initial implementation from plan",
            diff=diff_summary(previous_code, code),
        )
    )
    return {"code": code, "trace": trace}


def tester_node(state: AgentState) -> dict:
    test_result = run_tests(state["code"])

    round_number = state.get("critique_round", 0) + 1
    trace = list(state.get("trace", []))
    trace.append(
        log_event(
            "tester",
            event="ran_tests",
            round=round_number,
            passed=test_result["passed"],
            exit_code=test_result["exit_code"],
            stderr_excerpt=test_result["stderr"][:300],
        )
    )
    return {"test_result": test_result, "trace": trace}


def reviewer_node(state: AgentState) -> dict:
    review = review_code(state["code"], state["test_result"])
    round_number = state.get("critique_round", 0) + 1

    history = list(state.get("critique_history", []))
    history.append(
        {
            "round_number": round_number,
            "code_snapshot": state["code"],
            "reviewer_feedback": review["feedback"],
            "verdict": review["verdict"],
        }
    )

    trace = list(state.get("trace", []))
    trace.append(
        log_event(
            "reviewer",
            event="reviewed",
            round=round_number,
            verdict=review["verdict"],
            reason=review["feedback"],
        )
    )

    return {
        "review_verdict": review["verdict"],
        "review_feedback": review["feedback"],
        "critique_round": round_number,
        "critique_history": history,
        "trace": trace,
    }


def route_after_review(state: AgentState) -> Literal["revise", "done"]:
    max_rounds = state.get("critique_max_rounds", DEFAULT_MAX_ROUNDS)
    if state["review_verdict"] == "approve":
        return "done"
    if state["critique_round"] >= max_rounds:
        return "done"
    return "revise"


def build_critique_loop_graph():
    graph = StateGraph(AgentState)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)
    graph.add_node("reviewer", reviewer_node)

    graph.add_edge(START, "coder")
    graph.add_edge("coder", "tester")
    graph.add_edge("tester", "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        route_after_review,
        {"revise": "coder", "done": END},
    )

    return graph.compile()


def run_critique_loop(
    plan: str,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    human_feedback: str | None = None,
) -> AgentState:
    """Standalone entry point for testing the critique loop in isolation
    (Phase 3), before it's wired into the outer supervisor graph (Phase 4).
    """
    graph = build_critique_loop_graph()
    initial_state: AgentState = {
        "plan": plan,
        "critique_round": 0,
        "critique_max_rounds": max_rounds,
        "critique_history": [],
        "trace": [],
    }
    if human_feedback:
        initial_state["review_feedback"] = human_feedback

    return graph.invoke(initial_state, config={"recursion_limit": max_rounds * 4 + 10})
