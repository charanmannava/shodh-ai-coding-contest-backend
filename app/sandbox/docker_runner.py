import logging
import os
import shlex
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    verdict: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


class DockerRunner:
    def __init__(
        self,
        image: str | None = None,
        timeout_seconds: float | None = None,
        max_output_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.image = image or settings.judge_image
        self.timeout_seconds = timeout_seconds or settings.judge_timeout_seconds
        self.max_output_bytes = max_output_bytes or settings.judge_max_output_bytes
        self.temp_dir = Path(settings.judge_temp_dir)

    def run(self, code: str, stdin: str) -> RunResult:
        self.temp_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        with (
            tempfile.TemporaryDirectory(prefix="run-", dir=self.temp_dir) as work,
            tempfile.TemporaryDirectory(prefix="output-", dir=self.temp_dir) as output,
        ):
            workdir = Path(work)
            output_dir = Path(output)
            workdir.chmod(0o755)
            output_dir.chmod(0o777)
            code_path = workdir / "main.py"
            code_path.write_text(code, encoding="utf-8")
            code_path.chmod(0o444)
            input_path = workdir / "stdin.txt"
            input_path.write_text(stdin, encoding="utf-8")
            input_path.chmod(0o444)

            compile_result = self._run_container(
                workdir,
                output_dir,
                [
                    "python",
                    "-I",
                    "-c",
                    "import ast,pathlib; ast.parse(pathlib.Path('/workspace/main.py').read_text())",
                ],
            )
            if compile_result.verdict != "OK" or compile_result.exit_code != 0:
                if compile_result.verdict != "OK":
                    verdict = compile_result.verdict
                else:
                    verdict = "COMPILATION_ERROR"
                return RunResult(
                    verdict,
                    stderr=_decode(compile_result.stderr[: self.max_output_bytes]),
                    exit_code=compile_result.exit_code,
                )

            result = self._run_container(
                workdir,
                output_dir,
                ["python", "-I", "/workspace/main.py"],
            )
            if result.verdict != "OK":
                return RunResult(
                    result.verdict,
                    stdout=_decode(result.stdout[: self.max_output_bytes]),
                    stderr=_decode(result.stderr[: self.max_output_bytes]),
                    exit_code=result.exit_code,
                )
            if result.exit_code != 0:
                return RunResult(
                    "RUNTIME_ERROR",
                    stdout=_decode(result.stdout[: self.max_output_bytes]),
                    stderr=_decode(result.stderr[: self.max_output_bytes]),
                    exit_code=result.exit_code,
                )
            return RunResult(
                "OK",
                stdout=_decode(result.stdout[: self.max_output_bytes]),
                stderr=_decode(result.stderr[: self.max_output_bytes]),
                exit_code=result.exit_code,
            )

    def _run_container(
        self, workdir: Path, output_dir: Path, command: list[str]
    ) -> "_ProcessResult":
        client: docker.DockerClient | None = None
        container: Container | None = None
        stdout_path = output_dir / "stdout"
        stderr_path = output_dir / "stderr"
        wrapped_command = [
            "/bin/sh",
            "-c",
            "exec "
            + shlex.join(command)
            + " < /workspace/stdin.txt > /output/stdout 2> /output/stderr",
        ]
        try:
            client = _docker_client()
            container = client.containers.create(
                image=self.image,
                command=wrapped_command,
                detach=True,
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=32,
                mem_limit="128m",
                nano_cpus=500_000_000,
                shm_size="1m",
                ulimits=[
                    docker.types.Ulimit(name="cpu", soft=2, hard=2),
                    docker.types.Ulimit(
                        name="fsize",
                        soft=self.max_output_bytes + 1,
                        hard=self.max_output_bytes + 1,
                    ),
                    docker.types.Ulimit(name="nofile", soft=64, hard=64),
                ],
                user="65534:65534",
                tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
                volumes={
                    str(workdir): {"bind": "/workspace", "mode": "ro"},
                    str(output_dir): {"bind": "/output", "mode": "rw"},
                },
                working_dir="/workspace",
                environment={"PYTHONDONTWRITEBYTECODE": "1"},
                tty=False,
                auto_remove=False,
            )
            container.start()
            deadline = time.monotonic() + self.timeout_seconds
            timed_out = False
            output_limited = False
            while True:
                container.reload()
                if _combined_size(stdout_path, stderr_path) > self.max_output_bytes:
                    output_limited = True
                    break
                if container.status == "exited":
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(0.02)

            if timed_out or output_limited:
                try:
                    container.kill()
                except NotFound:
                    pass
                except APIError as exc:
                    if exc.status_code != 409:
                        raise
            exit_code = int(container.wait(timeout=5)["StatusCode"])
            stdout = _read_limited(stdout_path, self.max_output_bytes)
            stderr = _read_limited(stderr_path, self.max_output_bytes)
            if timed_out:
                return _ProcessResult("TIME_LIMIT_EXCEEDED", stdout, stderr, exit_code)
            if output_limited:
                return _ProcessResult("OUTPUT_LIMIT", stdout, stderr, exit_code)
            return _ProcessResult("OK", stdout, stderr, exit_code)
        except DockerException as exc:
            return _ProcessResult("JUDGE_ERROR", b"", str(exc).encode(), None)
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except NotFound:
                    pass
                except DockerException:
                    logger.exception(
                        "Could not remove judge container",
                        extra={"container_id": container.id},
                    )
            if client is not None:
                client.close()


def _docker_client() -> docker.DockerClient:
    host = os.environ.get("DOCKER_HOST")
    if host is None:
        candidates = [Path("/var/run/docker.sock"), Path.home() / ".docker/run/docker.sock"]
        socket_path = next((path for path in candidates if path.exists()), candidates[0])
        host = f"unix://{socket_path}"
    return docker.DockerClient(base_url=host, timeout=5)


def _combined_size(stdout_path: Path, stderr_path: Path) -> int:
    return sum(path.stat().st_size if path.exists() else 0 for path in (stdout_path, stderr_path))


def _read_limited(path: Path, maximum: int) -> bytes:
    if not path.exists():
        return b""
    with path.open("rb") as stream:
        return stream.read(maximum + 1)


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class _ProcessResult:
    verdict: str
    stdout: bytes
    stderr: bytes
    exit_code: int | None
