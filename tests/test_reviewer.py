from agents.reviewer import review_code

_GOOD_CODE = """
def add(a, b):
    \"\"\"Return the sum of a and b.\"\"\"
    return a + b

if __name__ == "__main__":
    assert add(2, 3) == 5
    print("ok")
"""

_PASSING_RESULT = {"passed": True, "stdout": "ok\n", "stderr": "", "exit_code": 0}

_FAILING_RESULT = {
    "passed": False,
    "stdout": "",
    "stderr": "AssertionError: deliberately wrong\n",
    "exit_code": 1,
}


def test_reviewer_approves_correct_passing_code():
    result = review_code(_GOOD_CODE, _PASSING_RESULT)
    assert result["verdict"] == "approve"


def test_reviewer_sends_back_on_failing_tests():
    result = review_code(_GOOD_CODE, _FAILING_RESULT)
    assert result["verdict"] == "revise"
    assert len(result["feedback"].strip()) > 0
