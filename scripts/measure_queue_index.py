import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings

ROWS = 20_000
QUEUED_ROWS = 20
QUEUE_QUERY = """
SELECT id
FROM judge_jobs
WHERE status = 'QUEUED' AND available_at <= now()
ORDER BY available_at, id
LIMIT 1
"""


def explain(connection) -> dict[str, object]:
    result = connection.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {QUEUE_QUERY}")
    ).scalar_one()
    return result[0]


def main() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            user_id = connection.execute(
                text("SELECT id FROM users WHERE email = 'loadtest-0001@loadtest.example.com'")
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO submissions (
                        id, user_id, contest_id, problem_version_id, suite_id, code,
                        status, idempotency_key, request_hash, created_at
                    )
                    SELECT
                        'plan-sub-' || lpad(n::text, 6, '0'),
                        :user_id,
                        '00000000-0000-4000-8000-000000000004',
                        '00000000-0000-4000-8000-000000000006',
                        '00000000-0000-4000-8000-000000000007',
                        '',
                        'COMPLETED',
                        'plan-key-' || lpad(n::text, 6, '0'),
                        repeat('a', 64),
                        now()
                    FROM generate_series(1, :rows) AS n
                    """
                ),
                {"user_id": user_id, "rows": ROWS},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO judge_attempts (
                        id, submission_id, attempt_number, status, created_at, completed_at
                    )
                    SELECT
                        'plan-attempt-' || lpad(n::text, 6, '0'),
                        'plan-sub-' || lpad(n::text, 6, '0'),
                        1,
                        'COMPLETED',
                        now(),
                        now()
                    FROM generate_series(1, :rows) AS n
                    """
                ),
                {"rows": ROWS},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO judge_jobs (
                        id, submission_id, attempt_id, status, retry_count, available_at
                    )
                    SELECT
                        'plan-job-' || lpad(n::text, 6, '0'),
                        'plan-sub-' || lpad(n::text, 6, '0'),
                        'plan-attempt-' || lpad(n::text, 6, '0'),
                        CASE WHEN n <= :queued_rows THEN 'QUEUED' ELSE 'COMPLETED' END,
                        0,
                        now() - interval '1 minute'
                    FROM generate_series(1, :rows) AS n
                    """
                ),
                {"rows": ROWS, "queued_rows": QUEUED_ROWS},
            )
            connection.execute(text("ANALYZE judge_jobs"))

            connection.execute(text("DROP INDEX ix_judge_jobs_queued_available"))
            before = explain(connection)
            connection.execute(
                text(
                    """
                    CREATE INDEX ix_judge_jobs_queued_available
                    ON judge_jobs (available_at, id)
                    WHERE status = 'QUEUED'
                    """
                )
            )
            connection.execute(text("ANALYZE judge_jobs"))
            after = explain(connection)
            transaction.rollback()
        except Exception:
            transaction.rollback()
            raise
        finally:
            engine.dispose()

    report = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "method": "Transactional synthetic queue rows; all inserted rows and index DDL rolled back.",
        "judge_jobs_in_test_transaction": ROWS,
        "queued_jobs_in_test_transaction": QUEUED_ROWS,
        "query": "Oldest eligible queued job, ordered by available_at and id.",
        "before_queue_index": before,
        "after_queue_index": after,
    }
    output = Path("results/queue-query-plan.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
