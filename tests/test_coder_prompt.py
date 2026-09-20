from agents.coder import build_user_content


def test_prompt_includes_previous_code_and_feedback():
    text = build_user_content("the plan", "handle empty input", "def f(): pass")
    assert "the plan" in text
    assert "def f(): pass" in text
    assert "handle empty input" in text


def test_first_write_has_no_previous_code_section():
    text = build_user_content("the plan", None, None)
    assert "previous version" not in text
    assert "Feedback" not in text
