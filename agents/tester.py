"""Tester agent: executes the Coder's code, reports pass/fail + errors.

Deliberately not an LLM call — the Tester's job is to actually run the code
and report ground truth, which the Reviewer (an LLM) then interprets.
"""
from __future__ import annotations

from graph.state import TestResult
from sandbox.executor import execute_code


def run_tests(code: str, timeout: int | None = None) -> TestResult:
    if timeout is not None:
        return execute_code(code, timeout=timeout)
    return execute_code(code)
