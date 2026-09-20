"""Phase 8 — end-to-end tests against the real pipeline (real Planner,
Coder, Reviewer via Gemini; real Tester execution).

Covers, per the build brief:
  - varied task difficulty (easy / medium / hard)
  - a case where the critique loop needs multiple rounds before approval
  - a case where the Tester fails and the supervisor correctly routes back
    into a fresh critique-loop attempt
  - the human-rejection path, verifying the re-loop and that feedback is
    actually incorporated

For the two "forced" scenarios, a single Tester call is fault-injected to
fail (the Coder and Reviewer are always real) so the routing path is
exercised deterministically rather than hoping a real model gets it wrong
on the first try -- LLM correctness isn't reliably reproducible, but the
system's *routing behavior* when a failure occurs must be.
"""
from __future__ import annotations

import unittest.mock
from contextlib import contextmanager

import graph.critique_loop as critique_loop_module
from graph.critique_loop import run_critique_loop
from graph.supervisor import SupervisorSession, run_supervisor


@contextmanager
def _fail_first_tester_call():
    """Patch `critique_loop_module.run_tests` so its first invocation returns
    a failing TestResult, and every subsequent call runs the real Tester.
    Used to deterministically exercise a failure-routing path while keeping
    the Coder and Reviewer fully real."""
    real_run_tests = critique_loop_module.run_tests
    calls = {"n": 0}

    def wrapper(code, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"passed": False, "stdout": "", "stderr": "AssertionError: forced failure for testing", "exit_code": 1}
        return real_run_tests(code, *args, **kwargs)

    with unittest.mock.patch.object(critique_loop_module, "run_tests", wrapper):
        yield


# ---------------------------------------------------------------------------
# Varied task difficulty
# ---------------------------------------------------------------------------

def test_e2e_easy_task():
    task = "Write a function `is_even(n: int) -> bool` that returns True if n is even."
    session, state = run_supervisor(task, critique_max_rounds=2, supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert "def is_even" in payload["code"]

    final = session.resume(decision="approve")
    assert final["human_decision"] == "approve"
    print(f"\n[easy] steps={final['supervisor_step']} rounds={final['critique_round']}")


def test_e2e_medium_task():
    task = (
        "Write a function `merge_intervals(intervals: list[list[int]]) -> list[list[int]]` "
        "that merges all overlapping intervals and returns the merged list, sorted by start."
    )
    session, state = run_supervisor(task, critique_max_rounds=2, supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert "def merge_intervals" in payload["code"]

    final = session.resume(decision="approve")
    assert final["human_decision"] == "approve"
    print(f"\n[medium] steps={final['supervisor_step']} rounds={final['critique_round']}")


def test_e2e_hard_task():
    task = (
        "Write a function `next_greater_circular(nums: list[int]) -> list[int]` that, "
        "treating `nums` as circular (wrapping around once), returns a list where each "
        "element is replaced by the next greater element found by scanning forward "
        "(wrapping around the end back to the start once); use -1 if none exists."
    )
    session, state = run_supervisor(task, critique_max_rounds=2, supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert "def next_greater_circular" in payload["code"]

    final = session.resume(decision="approve")
    assert final["human_decision"] == "approve"
    print(f"\n[hard] steps={final['supervisor_step']} rounds={final['critique_round']}")


# ---------------------------------------------------------------------------
# Multi-round critique loop (real Coder + real Reviewer, Tester's first
# result fault-injected to force at least one revision round)
# ---------------------------------------------------------------------------

def test_e2e_multi_round_critique_with_real_agents():
    from agents.planner import plan as make_plan

    with _fail_first_tester_call():
        task = "Write a function `count_vowels(s: str) -> int` that counts vowels (a, e, i, o, u) case-insensitively."
        task_plan = make_plan(task)
        result = run_critique_loop(plan=task_plan, max_rounds=4)

    assert result["critique_round"] >= 2, "forced first-round failure must produce a second round"
    assert result["critique_history"][0]["verdict"] == "revise"
    assert result["test_result"]["passed"] is True
    assert "def count_vowels" in result["code"]
    print(f"\n[multi-round] rounds used={result['critique_round']}, history={[h['verdict'] for h in result['critique_history']]}")


# ---------------------------------------------------------------------------
# Supervisor-level retry on test failure (real Coder/Reviewer; critique_max_rounds=1
# so the critique loop can't self-heal within one attempt, forcing the supervisor's
# own retry-on-failure routing to fire)
# ---------------------------------------------------------------------------

def test_e2e_supervisor_retries_on_forced_test_failure():
    task = "Write a function `sum_digits(n: int) -> int` that returns the sum of the digits of a non-negative integer n."

    with _fail_first_tester_call():
        session, state = run_supervisor(task, critique_max_rounds=1, supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert payload["supervisor_step"] == 2, "must have retried once at the supervisor level"
    assert payload["test_result"]["passed"] is True

    decisions = [t["decision"] for t in state["trace"] if t.get("agent") == "supervisor"]
    assert decisions.count("critique_loop") == 2
    assert decisions.count("test_gate") == 2

    final = session.resume(decision="approve")
    assert final["human_decision"] == "approve"
    print(f"\n[supervisor retry] steps used={final['supervisor_step']}")


# ---------------------------------------------------------------------------
# Live human-rejection path: verify the re-loop happens and the human's
# feedback is actually incorporated into the revised code.
# ---------------------------------------------------------------------------

def test_e2e_human_rejection_loops_back_and_incorporates_feedback():
    task = "Write a function `square(n: int) -> int` that returns n squared."
    session, state = run_supervisor(task, critique_max_rounds=1, supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload1 = SupervisorSession.interrupt_payload(state)
    assert payload1["test_result"]["passed"] is True
    assert payload1["supervisor_step"] == 1

    state2 = session.resume(
        decision="reject",
        feedback="Add a complete docstring to the square function explaining its parameter and return value.",
    )

    assert SupervisorSession.is_paused(state2), "reject with steps remaining must loop back, not end"
    payload2 = SupervisorSession.interrupt_payload(state2)
    assert payload2["supervisor_step"] == 2
    assert '"""' in payload2["code"] or "'''" in payload2["code"], "revised code should now include the requested docstring"

    final = session.resume(decision="approve")
    assert not SupervisorSession.is_paused(final)
    assert final["human_decision"] == "approve"
    print(f"\n[human reject] steps used={final['supervisor_step']}")
