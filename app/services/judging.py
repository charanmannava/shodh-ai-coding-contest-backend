from dataclasses import dataclass

from app.sandbox.docker_runner import DockerRunner
from app.services.scoring import score_cases


@dataclass(frozen=True)
class JudgeResult:
    verdict: str
    score: int
    details: str


def judge_submission(
    code: str,
    cases: list[tuple[str, str]],
    runner: DockerRunner | None = None,
) -> JudgeResult:
    if not cases:
        return JudgeResult("JUDGE_ERROR", 0, "The pinned test suite is empty")
    runner = runner or DockerRunner()
    passed = 0
    first_failure: str | None = None
    for index, (stdin, expected) in enumerate(cases, start=1):
        result = runner.run(code, stdin)
        if result.verdict == "OK":
            actual_lines = result.stdout.strip().splitlines()
            expected_lines = expected.strip().splitlines()
            if actual_lines == expected_lines:
                passed += 1
            elif first_failure is None:
                first_failure = f"Test case {index}: output mismatch"
            continue
        if result.verdict == "OUTPUT_LIMIT":
            return JudgeResult("RUNTIME_ERROR", 0, f"Test case {index}: output limit exceeded")
        if result.verdict in {
            "COMPILATION_ERROR",
            "RUNTIME_ERROR",
            "TIME_LIMIT_EXCEEDED",
            "JUDGE_ERROR",
        }:
            return JudgeResult(result.verdict, 0, f"Test case {index}: {result.stderr[:1000]}")
        return JudgeResult("JUDGE_ERROR", 0, f"Unexpected runner verdict: {result.verdict}")

    score = score_cases(passed, len(cases))
    if passed == len(cases):
        return JudgeResult("ACCEPTED", score, "All test cases passed")
    return JudgeResult("WRONG_ANSWER", score, first_failure or "One or more tests failed")
