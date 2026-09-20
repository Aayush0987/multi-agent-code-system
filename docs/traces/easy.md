# Example run: easy

**Task:** Write a function `is_even(n: int) -> bool` that returns True if n is even.

**Supervisor steps:** 1  
**Critique rounds per step:** [1]  
**Wall time:** 6.4s  
**Final human decision:** approve

## Decision path

- Planner: generated initial plan
- Critique loop (supervisor step 1): 1 round(s), outcome=approve
    - round 1 Coder (wrote_code): 'initial implementation from plan'
    - round 1 Tester: passed (exit 0)
    - round 1 Reviewer: approve - 'The implementation is correct, clean, and all test cases passed successfully.'
- Test gate: passed
- Human checkpoint: approve

## Delivered code

```python
def is_even(n: int) -> bool:
    """Check if an integer is even."""
    return n % 2 == 0


if __name__ == "__main__":
    # Test cases covering positive, zero, and negative numbers
    assert is_even(0) == True
    assert is_even(2) == True
    assert is_even(3) == False
    assert is_even(-2) == True
    assert is_even(-3) == False
    assert is_even(4) == True
    assert is_even(1) == False

    print("All tests passed successfully!")
```
