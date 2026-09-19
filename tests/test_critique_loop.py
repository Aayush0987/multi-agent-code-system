"""Phase 3 tests for the Coder<->Reviewer critique loop.

Two kinds of coverage:
  - Deterministic unit tests that monkeypatch the Coder/Tester/Reviewer so
    the loop's *control flow* (rounds, bound enforcement, history logging)
    is verified without depending on real LLM behavior.
  - One live smoke test against the real Groq-backed agents to confirm the
    wiring works end-to-end.
"""
from __future__ import annotations

import graph.critique_loop as critique_loop_module
from graph.critique_loop import run_critique_loop


def _patch_agents(monkeypatch, coder_outputs, verdicts):
    """coder_outputs: list of code strings returned on each Coder call.
    verdicts: list of (verdict, feedback) tuples returned on each Reviewer call.
    """
    coder_calls = {"n": 0}
    reviewer_calls = {"n": 0}

    def fake_write_code(plan, feedback=None):
        code = coder_outputs[coder_calls["n"]]
        coder_calls["n"] += 1
        return code

    def fake_run_tests(code, timeout=None):
        return {"passed": True, "stdout": "ok", "stderr": "", "exit_code": 0}

    def fake_review_code(code, test_result):
        verdict, feedback = verdicts[reviewer_calls["n"]]
        reviewer_calls["n"] += 1
        return {"verdict": verdict, "feedback": feedback}

    monkeypatch.setattr(critique_loop_module, "write_code", fake_write_code)
    monkeypatch.setattr(critique_loop_module, "run_tests", fake_run_tests)
    monkeypatch.setattr(critique_loop_module, "review_code", fake_review_code)


def test_loop_stops_immediately_on_first_approval(monkeypatch):
    _patch_agents(
        monkeypatch,
        coder_outputs=["code v1"],
        verdicts=[("approve", "looks good")],
    )

    result = run_critique_loop(plan="dummy plan", max_rounds=3)

    assert result["review_verdict"] == "approve"
    assert result["critique_round"] == 1
    assert len(result["critique_history"]) == 1
    assert result["code"] == "code v1"


def test_loop_revises_then_approves(monkeypatch):
    _patch_agents(
        monkeypatch,
        coder_outputs=["code v1", "code v2"],
        verdicts=[("revise", "fix the bug"), ("approve", "now correct")],
    )

    result = run_critique_loop(plan="dummy plan", max_rounds=3)

    assert result["review_verdict"] == "approve"
    assert result["critique_round"] == 2
    assert len(result["critique_history"]) == 2
    assert result["critique_history"][0]["verdict"] == "revise"
    assert result["critique_history"][0]["reviewer_feedback"] == "fix the bug"
    assert result["critique_history"][1]["verdict"] == "approve"
    assert result["code"] == "code v2"


def test_loop_bounded_by_max_rounds_without_approval(monkeypatch):
    _patch_agents(
        monkeypatch,
        coder_outputs=["v1", "v2", "v3"],
        verdicts=[("revise", "still wrong"), ("revise", "still wrong"), ("revise", "still wrong")],
    )

    result = run_critique_loop(plan="dummy plan", max_rounds=3)

    # Never approved, but the loop must not exceed the configured bound.
    assert result["review_verdict"] == "revise"
    assert result["critique_round"] == 3
    assert len(result["critique_history"]) == 3


def test_live_critique_loop_end_to_end():
    """Smoke test against real Groq-backed agents (Phase 2 agents wired
    together). Not deterministic on round count, but must terminate within
    the bound and produce a consistent trace.
    """
    from agents.planner import plan as make_plan

    task = (
        "Write a function `is_prime(n: int) -> bool` that correctly handles "
        "negative numbers, 0, and 1 (all False), and is reasonably efficient "
        "for large n."
    )
    task_plan = make_plan(task)

    result = run_critique_loop(plan=task_plan, max_rounds=3)

    assert result["critique_round"] >= 1
    assert result["critique_round"] <= 3
    assert len(result["critique_history"]) == result["critique_round"]
    assert result["review_verdict"] in ("approve", "revise")
    assert "def is_prime" in result["code"]
