"""Shared trace/event logging helpers used by both the critique loop and
the supervisor graph, so every iteration at both levels records not just
that it happened, but what changed and why."""
from __future__ import annotations

import difflib
import time
from typing import Any


def log_event(agent: str, **fields: Any) -> dict:
    """Build one structured trace entry. `agent` identifies which
    agent/graph-level actor produced it; remaining fields are event-specific
    (e.g. `decision=...` for supervisor routing, `event=...` + `reason=...`
    + `diff=...` for an agent's actual work)."""
    return {"timestamp": time.time(), "agent": agent, **fields}


def diff_summary(old_code: str | None, new_code: str, context_lines: int = 2, max_lines: int = 40) -> str:
    """A truncated unified diff between two code versions, for the trace's
    "what changed" record. Returns a human-readable placeholder when there's
    no prior version (round 1) or no actual change."""
    if not old_code:
        return "(initial version, no prior code to diff against)"

    diff_lines = list(
        difflib.unified_diff(
            old_code.splitlines(),
            new_code.splitlines(),
            lineterm="",
            n=context_lines,
        )
    )
    if not diff_lines:
        return "(no changes)"

    truncated = diff_lines[:max_lines]
    text = "\n".join(truncated)
    if len(diff_lines) > max_lines:
        text += f"\n... ({len(diff_lines) - max_lines} more diff lines truncated)"
    return text
