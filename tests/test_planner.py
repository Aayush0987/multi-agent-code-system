from agents.planner import plan


def test_planner_produces_nonempty_structured_plan(fixed_task):
    result = plan(fixed_task)
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    # Loosely check it looks like a step-by-step plan, not free prose.
    assert any(marker in result for marker in ("1.", "1)", "- ", "Step 1"))
