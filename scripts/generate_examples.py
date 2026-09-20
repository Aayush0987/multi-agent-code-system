"""Runs the pipeline on a set of tasks and writes example traces + stats
to docs/traces/ for the README.

Usage: uv run python -m scripts.generate_examples

Scenarios:
  - easy / medium / hard: clean runs, human approves
  - multi_round: first Tester result fault-injected to fail, so the critique
    loop needs a second round (Coder and Reviewer are real)
  - human_rejection: human rejects passing code with feedback, then approves

The two fault-injected/human scenarios exist to exercise routing paths
reliably; real models often get simple tasks right on the first try.
"""
from __future__ import annotations

import json
import time
import unittest.mock
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

import graph.critique_loop as critique_loop_module
from graph.observability import compute_timing, walk_trace
from graph.supervisor import SupervisorSession, run_supervisor

load_dotenv()

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "traces"

TASKS = {
    "easy": "Write a function `is_even(n: int) -> bool` that returns True if n is even.",
    "medium": (
        "Write a function `merge_intervals(intervals: list[list[int]]) -> list[list[int]]` "
        "that merges all overlapping intervals and returns the merged list, sorted by start."
    ),
    "hard": (
        "Write a function `next_greater_circular(nums: list[int]) -> list[int]` that, "
        "treating `nums` as circular (wrapping around once), returns a list where each "
        "element is replaced by the next greater element found by scanning forward "
        "(wrapping around the end back to the start once); use -1 if none exists."
    ),
    "multi_round": "Write a function `count_vowels(s: str) -> int` that counts vowels (a, e, i, o, u) case-insensitively.",
    "human_rejection": "Write a function `square(n: int) -> int` that returns n squared.",
}


@contextmanager
def _fail_first_tester_call():
    real_run_tests = critique_loop_module.run_tests
    calls = {"n": 0}

    def wrapper(code, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"passed": False, "stdout": "", "stderr": "AssertionError: forced failure for testing", "exit_code": 1}
        return real_run_tests(code, *args, **kwargs)

    with unittest.mock.patch.object(critique_loop_module, "run_tests", wrapper):
        yield


def _render_trace(state: dict) -> str:
    lines = []
    for section in walk_trace(state["trace"]):
        m = section["macro"]
        d = m["decision"]
        if d == "planner":
            lines.append("- Planner: generated initial plan")
        elif d == "critique_loop":
            lines.append(
                f"- Critique loop (supervisor step {m['supervisor_step']}): "
                f"{m['critique_rounds_used']} round(s), outcome={m['critique_outcome']}"
            )
            for e in section["rounds"]:
                if e["agent"] == "coder":
                    lines.append(f"    - round {e['round']} Coder ({e['event']}): {e['reason'][:100]!r}")
                elif e["agent"] == "tester":
                    lines.append(f"    - round {e['round']} Tester: {'passed' if e['passed'] else 'FAILED'} (exit {e['exit_code']})")
                elif e["agent"] == "reviewer":
                    lines.append(f"    - round {e['round']} Reviewer: {e['verdict']} - {e['reason'][:100]!r}")
        elif d == "test_gate":
            lines.append(f"- Test gate: {'passed' if m['passed'] else 'failed'}")
        elif d == "human_checkpoint":
            lines.append(f"- Human checkpoint: {m['human_decision']}")
    return "\n".join(lines)


def _run(name: str) -> dict:
    task = TASKS[name]
    start = time.time()

    if name == "multi_round":
        with _fail_first_tester_call():
            session, state = run_supervisor(task, critique_max_rounds=3, supervisor_max_steps=2)
            state = session.resume(decision="approve")
    elif name == "human_rejection":
        session, state = run_supervisor(task, critique_max_rounds=1, supervisor_max_steps=3)
        state = session.resume(
            decision="reject",
            feedback="Add a complete docstring to the square function explaining its parameter and return value.",
        )
        state = session.resume(decision="approve")
    else:
        session, state = run_supervisor(task, critique_max_rounds=3, supervisor_max_steps=2)
        state = session.resume(decision="approve")

    assert not SupervisorSession.is_paused(state)
    elapsed = time.time() - start

    macro = [e for e in state["trace"] if e.get("agent") == "supervisor" and e.get("decision") == "critique_loop"]
    return {
        "name": name,
        "task": task,
        "supervisor_steps": state["supervisor_step"],
        "critique_rounds_per_step": [e["critique_rounds_used"] for e in macro],
        "human_decision": state["human_decision"],
        "wall_seconds": round(elapsed, 1),
        "timing_by_agent": compute_timing(state["trace"])["totals_by_agent"],
        "trace_text": _render_trace(state),
        "final_code": state["code"],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for name in TASKS:
        print(f"running {name}...")
        result = _run(name)
        results.append(result)
        (OUT_DIR / f"{name}.md").write_text(
            f"# Example run: {name}\n\n**Task:** {result['task']}\n\n"
            f"**Supervisor steps:** {result['supervisor_steps']}  \n"
            f"**Critique rounds per step:** {result['critique_rounds_per_step']}  \n"
            f"**Wall time:** {result['wall_seconds']}s  \n"
            f"**Final human decision:** {result['human_decision']}\n\n"
            f"## Decision path\n\n{result['trace_text']}\n\n"
            f"## Delivered code\n\n```python\n{result['final_code']}\n```\n"
        )
        time.sleep(3)

    (OUT_DIR / "stats.json").write_text(
        json.dumps(
            [{k: v for k, v in r.items() if k not in ("trace_text", "final_code")} for r in results],
            indent=2,
        )
    )
    print(f"wrote {len(results)} traces to {OUT_DIR}")


if __name__ == "__main__":
    main()
