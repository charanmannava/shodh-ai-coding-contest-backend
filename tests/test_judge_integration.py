import os

import pytest

from app.sandbox.docker_runner import DockerRunner

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DOCKER_TESTS") != "1",
    reason="Set RUN_DOCKER_TESTS=1 to run the real Docker sandbox integration tests",
)


def test_real_python_container_runs_non_root_with_no_network():
    result = DockerRunner().run("print(input().strip())", "hello\n")

    assert result.verdict == "OK"
    assert result.stdout == "hello\n"


def test_real_python_container_enforces_wall_clock_limit():
    result = DockerRunner(timeout_seconds=0.5).run("while True: pass", "")

    assert result.verdict == "TIME_LIMIT_EXCEEDED"


def test_real_python_container_reports_syntax_errors():
    result = DockerRunner().run("def unfinished(:\n    pass", "")

    assert result.verdict == "COMPILATION_ERROR"
    assert "SyntaxError" in result.stderr


def test_real_python_container_enforces_output_limit():
    result = DockerRunner(max_output_bytes=1024).run("while True: print('x' * 1024)", "")

    assert result.verdict == "OUTPUT_LIMIT"
    assert len(result.stdout.encode("utf-8")) <= 1024
