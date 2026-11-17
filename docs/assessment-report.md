# Assessment verification report

Captured results from the local Docker Compose environment. These are repeatable development measurements, not production capacity claims.

## Environment and workload

- Run date: 2026-11-17 UTC
- Git revision: unavailable (workspace is not a Git repository)
- API / worker / database / Docker: Python 3.12 containers, PostgreSQL 16.16, Docker Engine 29.9.2
- Benchmark client: Python 3.14.10 on macOS 27.2.1 arm64, 10 logical CPUs
- Users: 10 distinct benchmark participants
- Submissions: 100
- Request mix: 100 `POST /submissions`; 2,556 `GET /submissions/{id}` polls
- Concurrency: 20
- Run duration: 35.47 seconds
- Host memory/storage: not recorded

## API and queue measurements

- API latency p50 / p95 / p99: 8.02 / 18.27 / 53.29 ms
- Throughput: 74.88 requests/second
- API errors: 0 (0%); failed submissions: 0; completed submissions: 100; judge errors: 0
- Observed queue-delay p50 / p95 / p99: 6.22 / 6.48 / 7.04 seconds
- Queue delay is submission creation to first observed non-`QUEUED` status and includes the 250 ms polling interval.
- Artifact: [load-test.json](../results/load-test.json)

## Database bottleneck and improvement

- Query: claim the oldest available queued job, ordered by `available_at, id`.
- Dataset: 20,000 synthetic jobs in a transaction, including 20 queued jobs; inserts and index DDL rolled back.
- Before: status-index scan followed by top-N sort; execution 0.020 ms, 13 shared-hit blocks.
- After: `ix_judge_jobs_queued_available` index-only scan; execution 0.010 ms, 2 shared-hit and 1 shared-read block.
- Improvement: the partial index matched the queue order and removed the sort in this synthetic plan. This is a focused query-plan comparison, not a production bottleneck or end-to-end throughput claim.
- Full captured plans: [queue-query-plan.json](../results/queue-query-plan.json)

## Deterministic and failure verification

- Deterministic seed: contest `00000000-0000-4000-8000-000000000004`, problem `00000000-0000-4000-8000-000000000005`; benchmark-user creation verified 10 accounts.
- Unit/API/reliability suite: 17 passed, 5 environment-gated tests skipped.
- Real Docker runner tests: 4 passed, including output limit and execution timeout.
- Two-process PostgreSQL `SKIP LOCKED` claim test: 1 passed.
- Worker crash/lease recovery and transient judge failure/retry: covered by passing worker tests in the unit/API suite.
- API health after rebuild: `{"status":"ok"}`; two worker processes were running for the benchmark.
- A Starlette deprecation warning about the installed `httpx` test client was emitted; it did not fail tests.
