"""Phase 7 tests for trace persistence, walking, and timing -- deterministic,
built on a synthetic trace so they don't depend on real LLM timing."""
from __future__ import annotations

import json

from graph.observability import compute_timing, load_run_log, save_run_log, walk_trace


def _synthetic_trace():
    return [
        {"timestamp": 100.0, "agent": "supervisor", "decision": "planner", "reason": "task received"},
        {"timestamp": 101.0, "agent": "supervisor", "decision": "critique_loop", "supervisor_step": 1, "critique_rounds_used": 2, "critique_outcome": "approve"},
        {"timestamp": 101.5, "agent": "coder", "event": "wrote_code", "round": 1, "reason": "initial implementation from plan"},
        {"timestamp": 102.0, "agent": "tester", "event": "ran_tests", "round": 1, "passed": False, "exit_code": 1},
        {"timestamp": 102.5, "agent": "reviewer", "event": "reviewed", "round": 1, "verdict": "revise", "reason": "fix the bug"},
        {"timestamp": 103.0, "agent": "coder", "event": "revised_code", "round": 2, "reason": "fix the bug"},
        {"timestamp": 103.5, "agent": "tester", "event": "ran_tests", "round": 2, "passed": True, "exit_code": 0},
        {"timestamp": 104.0, "agent": "reviewer", "event": "reviewed", "round": 2, "verdict": "approve", "reason": "looks good"},
        {"timestamp": 104.5, "agent": "supervisor", "decision": "test_gate", "passed": True},
        {"timestamp": 105.0, "agent": "supervisor", "decision": "human_checkpoint", "human_decision": "approve"},
    ]


def test_walk_trace_groups_rounds_under_their_macro_step():
    sections = walk_trace(_synthetic_trace())

    decisions = [s["macro"]["decision"] for s in sections]
    assert decisions == ["planner", "critique_loop", "test_gate", "human_checkpoint"]

    critique_section = sections[1]
    assert len(critique_section["rounds"]) == 6  # 2 rounds x (coder, tester, reviewer)
    assert critique_section["rounds"][0]["agent"] == "coder"
    assert critique_section["rounds"][-1]["verdict"] == "approve"

    # planner and test_gate/human_checkpoint sections have no nested rounds
    assert sections[0]["rounds"] == []
    assert sections[2]["rounds"] == []


def test_compute_timing_attributes_gaps_to_the_agent_that_logged_next():
    timing = compute_timing(_synthetic_trace())

    assert set(timing["totals_by_agent"]) == {"supervisor", "coder", "tester", "reviewer"}
    total = sum(timing["totals_by_agent"].values())
    assert total == 5.0  # 105.0 - 100.0, first event contributes 0
    assert len(timing["timeline"]) == 10


def test_save_and_load_run_log_roundtrip(tmp_path, monkeypatch):
    import graph.observability as obs

    monkeypatch.setattr(obs, "LOGS_DIR", tmp_path)

    state = {
        "supervisor_step": 1,
        "human_decision": "approve",
        "review_verdict": "approve",
        "test_result": {"passed": True},
        "code": "def f(): pass",
        "trace": _synthetic_trace(),
    }
    path = save_run_log("test-run-1", state, task="dummy task")

    assert path.exists()
    loaded = load_run_log(path)
    assert loaded["run_id"] == "test-run-1"
    assert loaded["task"] == "dummy task"
    assert loaded["test_passed"] is True
    assert len(loaded["trace"]) == 10
    # Must be plain JSON (no Python objects), i.e. re-parseable from disk text.
    json.loads(path.read_text())
