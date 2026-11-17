# Shodh AI Coding Contest Backend

FastAPI + PostgreSQL backend for organization-scoped programming contests. Submissions and their initial judge jobs commit in one database transaction; independent worker processes claim jobs with PostgreSQL `FOR UPDATE SKIP LOCKED`.

## Run locally with Docker Compose

1. Copy `.env.example` to `.env`, replace `JWT_SECRET` with a random secret, and keep `DATABASE_URL` as shown (Compose supplies the database hostname).
2. Build the restricted Python image and start the API, database, migrations, and two workers:

   ```sh
   docker build -t contest-python:3.12 -f app/sandbox/Dockerfile .
   docker compose up --build --scale worker=2
   ```

   The API is available on port `8000`; PostgreSQL is published on host port `55432` to avoid conflicts with a local PostgreSQL service.

3. In another terminal, create the deterministic demo data:

   ```sh
   docker compose run --rm api python -m scripts.seed
   docker compose run --rm api python -m scripts.create_benchmark_users --count 10
   ```

4. Visit `http://localhost:8000/docs`. Demo accounts:

   - Organizer: `organizer@example.com` / `ChangeMe-Organizer-123!`
   - Participant: `participant@example.com` / `ChangeMe-Participant-123!`

   These credentials are for local evaluation only. Do not deploy the seed accounts or their passwords.

The migration service runs `alembic upgrade head` before API and worker startup. The database is persisted in the `postgres_data` Compose volume. `docker compose down -v` removes that data.

## API outline

All routes other than `/health` and `/auth/login` require `Authorization: Bearer <token>`.

| Method | Route | Access |
|---|---|---|
| POST | `/auth/login` | Public |
| GET / POST | `/contests` | Organization members / organizer or admin |
| POST | `/contests/{id}/join` | Organization members |
| POST | `/problems` | Organizer or admin |
| GET | `/problems/{id}?contest_id=...` | Contest member; only sample cases are returned |
| POST | `/submissions` | Joined participant; requires `Idempotency-Key` |
| GET | `/submissions/{id}` | Owner or same-organization organizer/admin |
| POST | `/submissions/{id}/rejudge` | Same-organization organizer/admin |
| GET | `/contests/{id}/leaderboard` | Organization member |

Contest creation may include `problem_ids`; the contest pins each selected problem version and test-suite ID. A submission independently records both pinned IDs, so later content changes cannot alter its judging inputs. There is intentionally no endpoint that returns hidden test cases.

Example submission body:

```json
{
  "contest_id": "contest-id",
  "problem_id": "problem-id",
  "code": "a, b = map(int, input().split())\nprint(a + b)"
}
```

The same participant and idempotency key return the original submission for an identical request; changing the payload with that key returns HTTP 409.

## Database and worker operations

The initial migration creates organizations, memberships, users, contests, participants, versioned problems and suites, cases, contest assignments, submissions, attempts, jobs, and verdicts. Additional contest/problem relationship rows make scoring and version pinning explicit.

Worker features include expiring leases for crashed-worker recovery, bounded retries for `JUDGE_ERROR`, immutable attempt history, and an authoritative-attempt pointer that only moves forward. Leaderboards read completed authoritative attempts, never queue messages.

The worker requires Docker Engine and access to its Docker socket. That socket grants broad host control; run judging workers on a dedicated host or isolated VM and do not mount the socket into the API service. Submitted code runs in a separate container with no network, a read-only root filesystem, a non-root UID, dropped capabilities, no-new-privileges, CPU/memory/PID/wall-clock/output limits, and a temporary directory cleaned after execution. Keep the runner image patched and do not run untrusted workloads on a shared developer workstation.

## Tests and verification

Install dependencies into a Python 3.12 environment, then run:

```sh
pip install -r requirements.txt
pytest -q
```

Unit/API tests use SQLite and fake runner results. To run real Docker integration tests against the locally built sandbox image:

```sh
RUN_DOCKER_TESTS=1 pytest -q tests/test_judge_integration.py
```

The multi-process claim test requires a migrated, disposable PostgreSQL test database:

```sh
TEST_DATABASE_URL=postgresql+psycopg://contest:contest@localhost:55432/contest pytest -q tests/test_concurrency.py
```

It starts two separate OS processes and asserts only one claims the same queued job. `tests/test_worker.py` exercises successful judging, a controlled transient infrastructure failure/retry, and reclaiming a job left running by a crashed worker after its lease expires.

## Repeatable load test

Create the deterministic local benchmark accounts with `python -m scripts.create_benchmark_users --count 10` (Docker Compose: `docker compose run --rm api python -m scripts.create_benchmark_users --count 10`). Each account's local-only password is `ChangeMe-Benchmark-123!`. The benchmark can log them in directly without printing tokens:

```sh
export BENCHMARK_PASSWORD='ChangeMe-Benchmark-123!'
python -m scripts.benchmark \
  --base-url http://localhost:8000 \
  --contest-id 00000000-0000-4000-8000-000000000004 \
  --problem-id 00000000-0000-4000-8000-000000000005 \
  --users 10 --submissions 100 --concurrency 20 \
  --login-email-template 'loadtest-{index:04d}@loadtest.example.com' \
  --password-env BENCHMARK_PASSWORD \
  --output results/load-test.json
```

For an existing deployment, omit `--login-email-template` and pass participant tokens through `ACCESS_TOKENS`.

The JSON records user/submission counts, request mix, concurrency, p50/p95/p99 and mean API latency, requests/second, error rate, and observed queue delay. Queue delay is polling-based (submission creation to first observed non-`QUEUED` status), so it includes the polling interval. The script does not claim results unless run; save actual outputs in `results/`.
The latest local run and its limitations are documented in [docs/assessment-report.md](docs/assessment-report.md).

## Query-plan measurement

The queue has targeted PostgreSQL partial indexes for queued availability and expired running leases. On a local benchmark database, run:

```sh
docker compose run --rm api python -m scripts.measure_queue_index
```

This script inserts 20,000 synthetic judge jobs and 20 queued rows inside one transaction, captures `EXPLAIN (ANALYZE, BUFFERS)` without the queued partial index, recreates the index, captures the second plan, and rolls everything back. It never removes an index from committed database state. The saved plan includes the artificial dataset size and is a focused index comparison, not a claim about a production bottleneck.
