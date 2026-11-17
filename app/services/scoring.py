def score_cases(passed: int, total: int) -> int:
    if total <= 0:
        raise ValueError("A judge suite must contain at least one test case")
    return passed * 100 // total
