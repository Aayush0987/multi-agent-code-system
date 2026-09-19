import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def fixed_task() -> str:
    """A single fixed task used across standalone agent tests (Phase 2)."""
    return (
        "Write a function `is_palindrome(s: str) -> bool` that returns True "
        "if the input string is a palindrome, ignoring case, spaces, and "
        "punctuation, and False otherwise."
    )
