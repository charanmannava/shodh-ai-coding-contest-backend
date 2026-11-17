import argparse
import asyncio
import json
import os
import platform
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


def percentile(values: list[float], percentage: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    tokens = [
        item.strip()
        for item in os.environ.get("ACCESS_TOKENS", os.environ.get("ACCESS_TOKEN", "")).split(",")
        if item.strip()
    ]
    latencies: list[float] = []
    queue_delays: list[float] = []
    api_errors = 0
    failed_submissions = 0
    completed_submissions = 0
    judge_errors = 0
    requests = {"POST /submissions": 0, "GET /submissions/{id}": 0}
    next_submission = 0
    lock = asyncio.Lock()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    timeout = httpx.Timeout(30.0)

    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        if len(tokens) < args.users:
            password = os.environ.get(args.password_env)
            if not args.login_email_template or not password:
                raise SystemExit(
                    "Provide ACCESS_TOKENS or set --login-email-template and "
                    f"{args.password_env} for benchmark-user logins."
                )
            for index in range(1, args.users + 1):
                email = args.login_email_template.format(index=index)
                response = await client.post(
                    "/auth/login",
                    json={"email": email, "password": password},
                )
                if response.status_code != 200:
                    raise SystemExit(f"Could not authenticate benchmark user {email}.")
                tokens.append(response.json()["access_token"])

        async def submit_one(index: int, token: str) -> None:
            nonlocal api_errors, failed_submissions, completed_submissions, judge_errors
            headers = {"Authorization": f"Bearer {token}"}
            payload = {
                "contest_id": args.contest_id,
                "problem_id": args.problem_id,
                "code": args.code,
            }
            submission_started = time.perf_counter()
            try:
                before = time.perf_counter()
                requests["POST /submissions"] += 1
                response = await client.post(
                    "/submissions",
                    json=payload,
                    headers={
                        **headers,
                        "Idempotency-Key": f"bench-{uuid.uuid4()}-{index}",
                    },
                )
                latencies.append(time.perf_counter() - before)
                if response.status_code != 202:
                    api_errors += 1
                    failed_submissions += 1
                    return
                submission_id = response.json()["submission_id"]
                queue_observed = False
                deadline = time.perf_counter() + args.completion_timeout
                while time.perf_counter() < deadline:
                    before = time.perf_counter()
                    requests["GET /submissions/{id}"] += 1
                    status_response = await client.get(
                        f"/submissions/{submission_id}", headers=headers
                    )
                    latencies.append(time.perf_counter() - before)
                    if status_response.status_code != 200:
                        api_errors += 1
                        failed_submissions += 1
                        return
                    status_value = status_response.json().get("status")
                    if status_value != "QUEUED" and not queue_observed:
                        queue_delays.append(time.perf_counter() - submission_started)
                        queue_observed = True
                    if status_value == "COMPLETED":
                        if status_response.json().get("verdict") == "JUDGE_ERROR":
                            judge_errors += 1
                            failed_submissions += 1
                        else:
                            completed_submissions += 1
                        return
                    await asyncio.sleep(args.poll_interval)
                failed_submissions += 1
            except httpx.HTTPError:
                api_errors += 1
                failed_submissions += 1

        async def worker(worker_index: int) -> None:
            nonlocal next_submission
            while True:
                async with lock:
                    if next_submission >= args.submissions:
                        return
                    index = next_submission
                    next_submission += 1
                await submit_one(index, tokens[worker_index % args.users])

        await asyncio.gather(
            *(
                worker(index)
                for index in range(min(args.concurrency, args.submissions))
            )
        )

    elapsed = time.perf_counter() - started
    report = {
        "started_at_utc": started_at,
        "base_url": args.base_url,
        "users": args.users,
        "submissions": args.submissions,
        "request_mix": requests,
        "concurrency": args.concurrency,
        "poll_interval_seconds": args.poll_interval,
        "completion_timeout_seconds": args.completion_timeout,
        "duration_seconds": elapsed,
        "requests_per_second": sum(requests.values()) / elapsed if elapsed else 0,
        "api_error_rate": api_errors / sum(requests.values()) if sum(requests.values()) else 0,
        "api_errors": api_errors,
        "failed_submissions": failed_submissions,
        "submission_failure_rate": failed_submissions / args.submissions if args.submissions else 0,
        "completed_submissions": completed_submissions,
        "judge_errors": judge_errors,
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "logical_cpu_count": os.cpu_count(),
        },
        "api_latency_seconds": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "mean": statistics.fmean(latencies) if latencies else None,
        },
        "queue_delay_seconds": {
            "p50": percentile(queue_delays, 50),
            "p95": percentile(queue_delays, 95),
            "p99": percentile(queue_delays, 99),
            "samples": len(queue_delays),
            "measurement": "Time until first observed non-QUEUED status; includes poll interval.",
        },
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Repeatable concurrent submission benchmark")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--contest-id", required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--submissions", type=int, default=100)
    parser.add_argument("--users", type=int, default=1, help="Number of distinct participant tokens")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--completion-timeout", type=float, default=120)
    parser.add_argument(
        "--login-email-template",
        help="Login one user per index (example: loadtest-{index:04d}@example.test)",
    )
    parser.add_argument(
        "--password-env",
        default="BENCHMARK_PASSWORD",
        help="Environment variable holding the local benchmark account password",
    )
    parser.add_argument("--code", default="a, b = map(int, input().split())\nprint(a + b)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.submissions < 1 or args.concurrency < 1 or args.users < 1:
        parser.error("submissions, concurrency, and users must be positive")
    report = asyncio.run(execute(args))
    formatted = json.dumps(report, indent=2)
    print(formatted)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
