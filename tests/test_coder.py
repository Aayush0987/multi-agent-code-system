from agents.coder import write_code
from agents.planner import plan


def test_coder_produces_runnable_code(fixed_task):
    task_plan = plan(fixed_task)
    code = write_code(task_plan)

    assert isinstance(code, str)
    assert len(code.strip()) > 0
    assert "def is_palindrome" in code
    assert "__main__" in code


def test_coder_revises_based_on_feedback(fixed_task):
    task_plan = plan(fixed_task)
    code = write_code(task_plan)

    feedback = (
        "Add a docstring to the is_palindrome function explaining the "
        "normalization rules (case, spaces, punctuation)."
    )
    revised = write_code(task_plan, feedback=feedback)

    assert "def is_palindrome" in revised
    assert '"""' in revised or "'''" in revised
