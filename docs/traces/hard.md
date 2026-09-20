# Example run: hard

**Task:** Write a function `next_greater_circular(nums: list[int]) -> list[int]` that, treating `nums` as circular (wrapping around once), returns a list where each element is replaced by the next greater element found by scanning forward (wrapping around the end back to the start once); use -1 if none exists.

**Supervisor steps:** 1  
**Critique rounds per step:** [1]  
**Wall time:** 10.7s  
**Final human decision:** approve

## Decision path

- Planner: generated initial plan
- Critique loop (supervisor step 1): 1 round(s), outcome=approve
    - round 1 Coder (wrote_code): 'initial implementation from plan'
    - round 1 Tester: passed (exit 0)
    - round 1 Reviewer: approve - 'All tests passed successfully and the implementation of the next greater element in a circular array'
- Test gate: passed
- Human checkpoint: approve

## Delivered code

```python
def next_greater_circular(nums: list[int]) -> list[int]:
    """
    Given a list of integers, returns a list of the same length where each
    element is replaced by the first strictly greater element in its circular traversal.
    If no such element exists, returns -1 for that position.
    """
    n = len(nums)
    if n == 0:
        return []
    
    res = [-1] * n
    stack = []
    
    # Traverse from 2 * n - 1 down to 0 to handle the circular array
    for i in range(2 * n - 1, -1, -1):
        idx = i % n
        # Pop elements from the stack that are less than or equal to the current element
        while stack and nums[stack[-1]] <= nums[idx]:
            stack.pop()
        
        # If this is part of the first pass (i < n), record the result
        if i < n:
            if stack:
                res[idx] = nums[stack[-1]]
            else:
                res[idx] = -1
        
        # Push the current index onto the stack
        stack.append(idx)
        
    return res


if __name__ == "__main__":
    # Test cases from the plan and requirements
    assert next_greater_circular([1, 2, 1]) == [2, -1, 2]
    assert next_greater_circular([5, 4, 3, 2, 1]) == [-1, 5, 5, 5, 5]
    assert next_greater_circular([4]) == [-1]
    assert next_greater_circular([]) == []
    assert next_greater_circular([2, 2, 2]) == [-1, -1, -1]
    assert next_greater_circular([3, 2, 1]) == [-1, 3, 3]  # Wait, let's trace [3, 2, 1] carefully:
    # 3: wrap around has no greater element -> -1
    # 2: wrap around finds 3 -> 3
    # 1: wrap around finds 2 (or 3? first strictly greater moving forward from 1 is 3).
    # Let's verify [3, 2, 1]:
    # from 1: next elements are 3 (wrap), so greater is 3.
    # from 2: next elements are 1, 3 (wrap), so greater is 3.
    # from 3: next elements are 2, 1, 3 (wrap), none greater.
    # So for [3, 2, 1], result should be [-1, 3, 3].
    assert next_greater_circular([3, 2, 1]) == [-1, 3, 3]

    print("All tests passed successfully!")
```
