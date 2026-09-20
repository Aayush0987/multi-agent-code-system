# Example run: human_rejection

**Task:** Write a function `square(n: int) -> int` that returns n squared.

**Supervisor steps:** 2  
**Critique rounds per step:** [1, 1]  
**Wall time:** 22.9s  
**Final human decision:** approve

## Decision path

- Planner: generated initial plan
- Critique loop (supervisor step 1): 1 round(s), outcome=approve
    - round 1 Coder (wrote_code): 'initial implementation from plan'
    - round 1 Tester: passed (exit 0)
    - round 1 Reviewer: approve - 'The code is correct, well-documented, includes comprehensive test assertions, and passed all tests s'
- Test gate: passed
- Human checkpoint: reject
- Critique loop (supervisor step 2): 1 round(s), outcome=approve
    - round 1 Coder (wrote_code): 'Add a complete docstring to the square function explaining its parameter and return value.'
    - round 1 Tester: passed (exit 0)
    - round 1 Reviewer: approve - 'The code is correct, well-documented, includes comprehensive assertions, and passed all tests succes'
- Test gate: passed
- Human checkpoint: approve

## Delivered code

```python
#!/usr/bin/env python3

def square(n: int) -> int:
    """
    Calculate the square of an integer.

    Parameters:
    n (int): The integer to square (can be positive, negative, or zero).

    Returns:
    int: The square of the input integer (n * n).
    """
    return n * n

if __name__ == "__main__":
    # Verify correctness using assert statements
    assert square(4) == 16, f"Expected 16, got {square(4)}"
    assert square(-3) == 9, f"Expected 9, got {square(-3)}"
    assert square(0) == 0, f"Expected 0, got {square(0)}"
    assert square(5) == 25, f"Expected 25, got {square(5)}"
    assert square(-5) == 25, f"Expected 25, got {square(-5)}"

    print("All tests passed successfully!")
```
