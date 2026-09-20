"""Phase 7 — trace persistence and summarization.

A run's `trace` (accumulated across the critique loop and supervisor graphs,
see `graph/trace.py`) is a flat, chronologically-appended list of events.
This module turns that into two useful views:

  - a saved JSON log per run, for later inspection
  - a "walked" summary that groups the flat trace back into its natural
    nested structure (supervisor macro steps, each containing its critique-
    loop rounds), plus a timing breakdown of where time was actually spent

Conceptual note: this trace data is exactly what an agent-trajectory
evaluation tool would consume -- which agent ran, how many loop iterations,
and where time went, independent of whether the final output was correct.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

_SUPERVISOR_DECISIONS = {"planner", "critique_loop", "test_gate", "human_checkpoint"}


def save_run_log(run_id: str, state: dict, task: str) -> Path:
    """Persist a run's final state (trace + outcome) as a JSON file under logs/."""
    LOGS_DIR.mkdir(exist_ok=True)
    path = LOGS_DIR / f"{run_id}.json"

    payload = {
        "run_id": run_id,
        "task": task,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "supervisor_step": state.get("supervisor_step"),
        "human_decision": state.get("human_decision"),
        "review_verdict": state.get("review_verdict"),
        "test_passed": (state.get("test_result") or {}).get("passed"),
        "code": state.get("code"),
        "trace": state.get("trace", []),
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def load_run_log(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def latest_run_log() -> Path | None:
    if not LOGS_DIR.exists():
        return None
    logs = sorted(LOGS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def walk_trace(trace: list[dict]) -> list[dict]:
    """Group the flat trace list back into macro steps (Planner, each
    critique-loop attempt, test gate, human checkpoint), each carrying its
    nested per-round Coder/Tester/Reviewer entries.

    Relies on insertion order: `critique_loop_node` appends its own summary
    marker immediately followed by that attempt's Coder/Tester/Reviewer
    entries (see `graph/supervisor.py`), so a single forward walk correctly
    nests them without needing to sort by timestamp.
    """
    sections: list[dict] = []
    current: dict | None = None

    for entry in trace:
        is_macro = entry.get("agent") == "supervisor" and entry.get("decision") in _SUPERVISOR_DECISIONS
        if is_macro:
            current = {"macro": entry, "rounds": []}
            sections.append(current)
        elif current is not None:
            current["rounds"].append(entry)

    return sections


def compute_timing(trace: list[dict]) -> dict:
    """Sort events chronologically and attribute the gap before each event
    to the agent that produced it (each event is logged right after that
    agent's work completes, so the preceding gap approximates its duration).
    Returns per-agent totals plus the ordered (agent, event, duration) list.
    """
    timed = sorted((e for e in trace if "timestamp" in e), key=lambda e: e["timestamp"])
    if not timed:
        return {"totals_by_agent": {}, "timeline": []}

    totals: dict[str, float] = {}
    timeline = []
    for i, entry in enumerate(timed):
        duration = entry["timestamp"] - timed[i - 1]["timestamp"] if i > 0 else 0.0
        agent = entry.get("agent", "unknown")
        totals[agent] = totals.get(agent, 0.0) + duration
        timeline.append(
            {
                "agent": agent,
                "label": entry.get("event") or entry.get("decision") or "?",
                "duration_seconds": round(duration, 3),
            }
        )

    return {"totals_by_agent": {k: round(v, 3) for k, v in totals.items()}, "timeline": timeline}
