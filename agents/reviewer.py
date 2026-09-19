"""Reviewer agent: code + test results -> verdict (approve / revise) + feedback.

This is the critic half of the Coder<->Reviewer debate/critique loop.
"""
from __future__ import annotations

import json
import re
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm, invoke_text
from graph.state import TestResult

_SYSTEM_PROMPT = """You are the Reviewer in a multi-agent coding system,
acting as critic to the Coder's proposals. Given the code and its test
execution result, judge correctness, quality, and whether it fulfills the
task. Be specific and actionable in feedback -- name the exact issue and
what to change, don't just say "improve this".

Rules:
  - If the test run failed (non-zero exit code, assertion error, exception),
    you MUST verdict "revise".
  - If the code is correct and reasonably clean, verdict "approve".
  - Otherwise, verdict "revise" with concrete, specific feedback.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{"verdict": "approve" | "revise", "feedback": "<specific feedback, or a short approval note>"}
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class ReviewResult(TypedDict):
    verdict: str
    feedback: str


def _parse_response(text: str) -> ReviewResult:
    match = _JSON_RE.search(text)
    raw = match.group(0) if match else text
    try:
        data = json.loads(raw)
        verdict = data.get("verdict", "revise").strip().lower()
        if verdict not in ("approve", "revise"):
            verdict = "revise"
        return ReviewResult(verdict=verdict, feedback=data.get("feedback", ""))
    except (json.JSONDecodeError, AttributeError):
        # Model didn't return valid JSON; fail safe to "revise" so the loop
        # doesn't silently approve on a parsing error.
        return ReviewResult(verdict="revise", feedback=f"Reviewer response was not parseable JSON: {text}")


def review_code(code: str, test_result: TestResult) -> ReviewResult:
    llm = get_llm(role="reviewer")

    user_content = (
        f"Code:\n```python\n{code}\n```\n\n"
        f"Test result:\n"
        f"  passed: {test_result['passed']}\n"
        f"  exit_code: {test_result['exit_code']}\n"
        f"  stdout: {test_result['stdout']}\n"
        f"  stderr: {test_result['stderr']}\n"
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    return _parse_response(invoke_text(llm, messages))
