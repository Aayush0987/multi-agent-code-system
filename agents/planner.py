"""Planner agent: task description -> structured step-by-step plan."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm import get_llm, invoke_text

_SYSTEM_PROMPT = """You are the Planner in a multi-agent coding system.
Given a coding task, break it down into a clear, numbered, step-by-step plan
for a Coder agent to follow. Cover:
  1. What the solution needs to do (inputs, outputs, edge cases)
  2. The high-level approach/algorithm
  3. What a self-contained correctness check (e.g. assertions in a
     `if __name__ == "__main__":` block) should verify

Keep it concise and actionable. Do not write code yourself — only the plan."""


def plan(task: str) -> str:
    llm = get_llm(role="planner")
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Task:\n{task}"),
    ]
    return invoke_text(llm, messages)
