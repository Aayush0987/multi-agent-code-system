from agents.tester import run_tests

_GOOD_CODE = """
def add(a, b):
    return a + b

if __name__ == "__main__":
    assert add(2, 3) == 5
    print("ok")
"""

_BAD_CODE = """
def add(a, b):
    return a + b

if __name__ == "__main__":
    assert add(2, 3) == 999, "deliberately wrong"
"""

_INFINITE_LOOP_CODE = """
if __name__ == "__main__":
    while True:
        pass
"""


def test_tester_reports_pass_on_good_code():
    result = run_tests(_GOOD_CODE)
    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert "ok" in result["stdout"]


def test_tester_reports_fail_on_bad_code():
    result = run_tests(_BAD_CODE)
    assert result["passed"] is False
    assert result["exit_code"] != 0
    assert "AssertionError" in result["stderr"]


def test_tester_times_out_infinite_loop():
    result = run_tests(_INFINITE_LOOP_CODE, timeout=2)
    assert result["passed"] is False
    assert "timed out" in result["stderr"]
