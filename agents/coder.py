"""Coder agent: plan (+ prior feedback) -> code.

Used both for the initial write (from the Planner's plan) and for revisions
inside the Coder<->Reviewer critique loop (from Reviewer/human feedback).
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm, invoke_text

_SYSTEM_PROMPT = """You are the Coder in a multi-agent coding system.
Given a plan (and, if present, feedback from a prior review or test run),
write a single self-contained Python script that implements the solution.

Requirements:
  - Output ONLY one ```python fenced code block, nothing else.
  - The script must be runnable standalone via `python solution.py`.
  - Include a `if __name__ == "__main__":` block that exercises the solution
    with concrete example(s) and uses `assert` statements to verify
    correctness. If any assertion fails, the script must exit non-zero.
  - If the script runs successfully with no assertion errors, it should
    print a short success message and exit 0.
  - Do not use any third-party packages — standard library only.
"""

_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _extract_code(text: str) -> str:
    match = _CODE_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    # Fallback: model didn't fence the code, return as-is.
    return text.strip()


def write_code(plan: str, feedback: str | None = None) -> str:
    llm = get_llm(role="coder")

    user_content = f"Plan:\n{plan}"
    if feedback:
        user_content += f"\n\nFeedback to address (from prior review/test run):\n{feedback}"

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    return _extract_code(invoke_text(llm, messages))
