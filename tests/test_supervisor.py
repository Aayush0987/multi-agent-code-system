"""Phase 4/5 tests for the outer Supervisor graph, including the real
human-in-the-loop interrupt/resume cycle.

Deterministic tests monkeypatch the Planner and the critique-loop subgraph's
`.invoke` so the *supervisor's own routing logic* (retry-on-failure, bound
enforcement, human approve/reject handling) is verified independently of
real LLM behavior. One live smoke test exercises the full real stack.
"""
from __future__ import annotations

import graph.supervisor as supervisor_module
from graph.supervisor import SupervisorSession, run_supervisor


def _canned_sub_result(passed: bool, verdict: str = "approve") -> dict:
    return {
        "code": f"code (passed={passed})",
        "test_result": {"passed": passed, "stdout": "", "stderr": "", "exit_code": 0 if passed else 1},
        "review_verdict": verdict,
        "review_feedback": "" if verdict == "approve" else "fix it",
        "critique_round": 1,
        "critique_history": [{"round_number": 1, "code_snapshot": "x", "reviewer_feedback": "", "verdict": verdict}],
        "trace": [],
    }


def _patch_planner(monkeypatch):
    monkeypatch.setattr(supervisor_module, "make_plan", lambda task: "dummy plan")


def _patch_critique_loop(monkeypatch, sub_results):
    calls = {"n": 0}

    def fake_invoke(sub_input, config=None):
        result = sub_results[calls["n"]]
        calls["n"] += 1
        return result

    monkeypatch.setattr(supervisor_module._critique_loop_graph, "invoke", fake_invoke)
    return calls


def _decisions(state):
    return [t["decision"] for t in state["trace"] if t.get("agent") == "supervisor"]


def test_supervisor_pauses_at_human_checkpoint_on_first_pass(monkeypatch):
    _patch_planner(monkeypatch)
    _patch_critique_loop(monkeypatch, [_canned_sub_result(passed=True)])

    session, state = run_supervisor(task="dummy task", supervisor_max_steps=3)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert payload["test_result"]["passed"] is True
    assert payload["supervisor_step"] == 1

    final_state = session.resume(decision="approve")
    assert not SupervisorSession.is_paused(final_state)
    assert final_state["human_decision"] == "approve"
    assert _decisions(final_state).count("critique_loop") == 1
    assert _decisions(final_state)[-1] == "human_checkpoint"


def test_supervisor_retries_on_test_failure_then_succeeds(monkeypatch):
    _patch_planner(monkeypatch)
    _patch_critique_loop(
        monkeypatch,
        [_canned_sub_result(passed=False, verdict="revise"), _canned_sub_result(passed=True)],
    )

    session, state = run_supervisor(task="dummy task", supervisor_max_steps=3)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert payload["test_result"]["passed"] is True
    assert payload["supervisor_step"] == 2
    assert _decisions(state).count("critique_loop") == 2
    assert _decisions(state).count("test_gate") == 2


def test_supervisor_bounded_by_max_steps_forces_end_even_on_reject(monkeypatch):
    _patch_planner(monkeypatch)
    _patch_critique_loop(
        monkeypatch,
        [
            _canned_sub_result(passed=False, verdict="revise"),
            _canned_sub_result(passed=False, verdict="revise"),
        ],
    )

    session, state = run_supervisor(task="dummy task", supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert payload["test_result"]["passed"] is False
    assert payload["supervisor_step"] == 2

    # Even though the human rejects, the retry budget is exhausted -- the
    # supervisor must still terminate rather than loop forever.
    final_state = session.resume(decision="reject", feedback="still broken")
    assert not SupervisorSession.is_paused(final_state)
    assert final_state["human_decision"] == "reject"
    assert final_state["supervisor_step"] == 2


def test_supervisor_reject_loops_back_then_approve_ends(monkeypatch):
    _patch_planner(monkeypatch)
    _patch_critique_loop(
        monkeypatch,
        [_canned_sub_result(passed=True), _canned_sub_result(passed=True)],
    )

    session, state = run_supervisor(task="dummy task", supervisor_max_steps=3)
    assert SupervisorSession.is_paused(state)
    assert state["__interrupt__"][0].value["supervisor_step"] == 1

    # Human rejects a passing-tests result on quality grounds -- should loop
    # back into a fresh critique-loop attempt with the human's feedback.
    state2 = session.resume(decision="reject", feedback="rename the function, it's unclear")
    assert SupervisorSession.is_paused(state2)
    payload2 = SupervisorSession.interrupt_payload(state2)
    assert payload2["supervisor_step"] == 2
    assert _decisions(state2).count("critique_loop") == 2

    final_state = session.resume(decision="approve")
    assert not SupervisorSession.is_paused(final_state)
    assert final_state["human_decision"] == "approve"
    assert final_state["supervisor_step"] == 2


def test_live_supervisor_end_to_end():
    task = (
        "Write a function `reverse_words(sentence: str) -> str` that reverses "
        "the order of words in a sentence, collapsing extra whitespace."
    )
    session, state = run_supervisor(task=task, critique_max_rounds=2, supervisor_max_steps=2)

    assert SupervisorSession.is_paused(state)
    payload = SupervisorSession.interrupt_payload(state)
    assert "def reverse_words" in payload["code"]
    assert 1 <= payload["supervisor_step"] <= 2

    final_state = session.resume(decision="approve")
    assert not SupervisorSession.is_paused(final_state)
    assert final_state["human_decision"] == "approve"
