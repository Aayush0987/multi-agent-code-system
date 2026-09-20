"""The outer Supervisor graph (macro orchestration).

Flow: Planner -> Coder/Reviewer critique loop (bounded inner loop, Phase 3)
-> test gate -> human checkpoint, with the supervisor routing back into a
fresh critique-loop attempt if the final code still fails its tests, bounded
by `supervisor_max_steps` (independent of the critique loop's own bound,
Phase 6).

The human checkpoint (Phase 5) is a real LangGraph `interrupt()`: execution
pauses, the caller (CLI) presents the final code/tests/verdict/history to a
human, and resumes the graph with the human's decision. Reject-with-feedback
routes back into a fresh critique-loop attempt (folding the human's feedback
into the Coder's next revision); approve ends the run. Both outcomes are
still bounded by `supervisor_max_steps` -- a human can't force unbounded
retries past the configured limit.
"""
from __future__ import annotations

import uuid
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agents.planner import plan as make_plan
from graph.critique_loop import build_critique_loop_graph
from graph.state import AgentState
from graph.trace import log_event

DEFAULT_SUPERVISOR_MAX_STEPS = 3
DEFAULT_CRITIQUE_MAX_ROUNDS = 3

_critique_loop_graph = build_critique_loop_graph()


def planner_node(state: AgentState) -> dict:
    generated_plan = make_plan(state["task"])
    trace = list(state.get("trace", []))
    trace.append(log_event("supervisor", decision="planner", reason="task received, no plan yet"))
    return {"plan": generated_plan, "trace": trace}


def critique_loop_node(state: AgentState) -> dict:
    """Run one full attempt of the bounded Coder<->Reviewer critique loop.

    Each supervisor-level retry gets a *fresh* set of critique rounds
    (critique_round reset to 0) rather than continuing to count against the
    previous attempt's rounds -- the two loop bounds are independent.
    """
    step = state.get("supervisor_step", 0) + 1

    sub_input: AgentState = {
        "plan": state["plan"],
        "critique_round": 0,
        "critique_max_rounds": state.get("critique_max_rounds", DEFAULT_CRITIQUE_MAX_ROUNDS),
        "critique_history": [],
        "trace": [],
    }
    # Carry forward feedback (from a failed test OR a human rejection) into
    # the first Coder call of this new attempt, if this is a retry.
    if state.get("review_feedback"):
        sub_input["review_feedback"] = state["review_feedback"]
    # ...and the code itself, so the Coder edits it rather than rewriting blind.
    if state.get("code"):
        sub_input["code"] = state["code"]

    sub_result = _critique_loop_graph.invoke(
        sub_input,
        config={"recursion_limit": sub_input["critique_max_rounds"] * 4 + 10},
    )

    trace = list(state.get("trace", []))
    trace.append(
        log_event(
            "supervisor",
            decision="critique_loop",
            supervisor_step=step,
            reason=(
                "initial attempt" if step == 1
                else f"prior attempt's code failed its tests or was rejected: {state.get('review_feedback', '')[:200]}"
            ),
            critique_rounds_used=sub_result["critique_round"],
            critique_outcome=sub_result["review_verdict"],
        )
    )
    trace.extend(sub_result.get("trace", []))

    return {
        "supervisor_step": step,
        "code": sub_result["code"],
        "test_result": sub_result["test_result"],
        "review_verdict": sub_result["review_verdict"],
        "review_feedback": sub_result["review_feedback"],
        "critique_round": sub_result["critique_round"],
        "critique_history": sub_result["critique_history"],
        "trace": trace,
        # Clear any prior human decision -- a fresh attempt needs a fresh checkpoint.
        "human_decision": None,
        "human_feedback": None,
    }


def test_gate_node(state: AgentState) -> dict:
    """Inspect the critique loop's final test result and log the supervisor's
    pass/fail gate decision (no code re-execution -- the result is already
    authoritative from the critique loop's last round)."""
    trace = list(state.get("trace", []))
    trace.append(
        log_event(
            "supervisor",
            decision="test_gate",
            passed=state["test_result"]["passed"],
            reason="gating on the critique loop's final test result before deciding retry vs. human checkpoint",
        )
    )
    return {"trace": trace}


def human_checkpoint_node(state: AgentState) -> dict:
    """Pause the graph and present the final artifact to a human.

    Expects the resume value (from `Command(resume=...)`) to be a dict of
    shape {"decision": "approve" | "reject", "feedback": str | None,
    "extra_steps": int}. `extra_steps` lets a rejecting human grant more
    supervisor steps when the budget is already used up.
    """
    payload = {
        "code": state["code"],
        "test_result": state["test_result"],
        "review_verdict": state["review_verdict"],
        "review_feedback": state["review_feedback"],
        "critique_history": state["critique_history"],
        "supervisor_step": state["supervisor_step"],
        "supervisor_max_steps": state.get("supervisor_max_steps", DEFAULT_SUPERVISOR_MAX_STEPS),
        "steps_remaining": state.get("supervisor_max_steps", DEFAULT_SUPERVISOR_MAX_STEPS)
        - state["supervisor_step"],
    }
    decision = interrupt(payload)

    trace = list(state.get("trace", []))
    trace.append(
        log_event(
            "supervisor",
            decision="human_checkpoint",
            human_decision=decision.get("decision"),
            reason=decision.get("feedback") or "human approved with no additional feedback",
        )
    )

    result: dict = {"human_decision": decision.get("decision"), "trace": trace}
    if decision.get("decision") == "reject":
        feedback = decision.get("feedback", "")
        result["human_feedback"] = feedback
        # Fold human feedback into the same channel the Coder reads for
        # revisions, same as a failed-test retry does.
        result["review_feedback"] = feedback

        max_steps = state.get("supervisor_max_steps", DEFAULT_SUPERVISOR_MAX_STEPS)
        extra = max(0, int(decision.get("extra_steps") or 0))
        if extra:
            max_steps += extra
            result["supervisor_max_steps"] = max_steps
        result["rejection_unapplied"] = state["supervisor_step"] >= max_steps
    else:
        result["rejection_unapplied"] = False
    return result


def route_after_test_gate(state: AgentState) -> Literal["retry", "human_checkpoint"]:
    max_steps = state.get("supervisor_max_steps", DEFAULT_SUPERVISOR_MAX_STEPS)
    if state["test_result"]["passed"]:
        return "human_checkpoint"
    if state["supervisor_step"] >= max_steps:
        return "human_checkpoint"  # bounded: deliver best-effort for human review
    return "retry"


def route_after_human_checkpoint(state: AgentState) -> Literal["retry", "end"]:
    max_steps = state.get("supervisor_max_steps", DEFAULT_SUPERVISOR_MAX_STEPS)
    if state.get("human_decision") == "reject" and state.get("supervisor_step", 0) < max_steps:
        return "retry"
    return "end"  # approved, or rejected but the retry budget is exhausted


def build_supervisor_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("planner", planner_node)
    graph.add_node("critique_loop", critique_loop_node)
    graph.add_node("test_gate", test_gate_node)
    graph.add_node("human_checkpoint", human_checkpoint_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "critique_loop")
    graph.add_edge("critique_loop", "test_gate")
    graph.add_conditional_edges(
        "test_gate",
        route_after_test_gate,
        {"retry": "critique_loop", "human_checkpoint": "human_checkpoint"},
    )
    graph.add_conditional_edges(
        "human_checkpoint",
        route_after_human_checkpoint,
        {"retry": "critique_loop", "end": END},
    )

    return graph.compile(checkpointer=checkpointer)


class SupervisorSession:
    """Stateful wrapper around one supervisor graph run, so a CLI (or test)
    can start it, react to a pause at the human checkpoint, and resume it
    without having to manage the checkpointer/thread_id/config directly."""

    def __init__(
        self,
        critique_max_rounds: int = DEFAULT_CRITIQUE_MAX_ROUNDS,
        supervisor_max_steps: int = DEFAULT_SUPERVISOR_MAX_STEPS,
        checkpointer=None,
        thread_id: str | None = None,
    ):
        self.checkpointer = checkpointer or MemorySaver()
        self.thread_id = thread_id or str(uuid.uuid4())
        self.graph = build_supervisor_graph(checkpointer=self.checkpointer)
        self.critique_max_rounds = critique_max_rounds
        self.supervisor_max_steps = supervisor_max_steps
        self._config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": supervisor_max_steps * 6 + 10,
        }

    def start(self, task: str) -> AgentState:
        initial_state: AgentState = {
            "task": task,
            "supervisor_step": 0,
            "supervisor_max_steps": self.supervisor_max_steps,
            "critique_max_rounds": self.critique_max_rounds,
            "trace": [],
        }
        return self.graph.invoke(initial_state, config=self._config)

    def resume(
        self,
        decision: Literal["approve", "reject"],
        feedback: str | None = None,
        extra_steps: int = 0,
    ) -> AgentState:
        return self.graph.invoke(
            Command(resume={"decision": decision, "feedback": feedback, "extra_steps": extra_steps}),
            config=self._config,
        )

    @staticmethod
    def is_paused(state: AgentState) -> bool:
        return bool(state.get("__interrupt__"))

    @staticmethod
    def interrupt_payload(state: AgentState) -> dict:
        return state["__interrupt__"][0].value


def run_supervisor(
    task: str,
    critique_max_rounds: int = DEFAULT_CRITIQUE_MAX_ROUNDS,
    supervisor_max_steps: int = DEFAULT_SUPERVISOR_MAX_STEPS,
) -> tuple[SupervisorSession, AgentState]:
    """Convenience entry point: starts a session and runs it up to the first
    pause (human checkpoint) or completion. Returns the session (so the
    caller can `.resume()` it) and the resulting state."""
    session = SupervisorSession(
        critique_max_rounds=critique_max_rounds,
        supervisor_max_steps=supervisor_max_steps,
    )
    return session, session.start(task)
