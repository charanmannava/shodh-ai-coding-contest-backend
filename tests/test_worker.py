from datetime import UTC, datetime
from datetime import timedelta

from app.models.judge_job import JudgeJob
from app.models.submission import JudgeAttempt, Submission
from app.sandbox.docker_runner import RunResult
from app.workers.judge_worker import JudgeWorker


class FakeRunner:
    def __init__(self, fail_once=False):
        self.fail_once = fail_once

    def run(self, code, stdin):
        if self.fail_once:
            self.fail_once = False
            return RunResult("JUDGE_ERROR", stderr="temporary runner error")
        values = [int(value) for value in stdin.split()]
        return RunResult("OK", stdout=f"{sum(values)}\n")


def create_queued_submission(session_factory, key):
    with session_factory() as session:
        submission = Submission(
            user_id="user-participant",
            contest_id="contest-one",
            problem_version_id="version-one",
            suite_id="suite-one",
            code="print(sum(map(int, input().split())))",
            idempotency_key=key,
            request_hash=key,
        )
        attempt = JudgeAttempt(attempt_number=1, status="QUEUED")
        submission.attempts.append(attempt)
        session.add(submission)
        session.flush()
        session.add(
            JudgeJob(
                submission_id=submission.id,
                attempt_id=attempt.id,
                status="QUEUED",
                available_at=datetime.now(UTC),
            )
        )
        session.commit()
        return submission.id, attempt.id


def test_worker_completes_and_publishes_authoritative_verdict(test_session_factory):
    submission_id, attempt_id = create_queued_submission(test_session_factory, "worker-success")
    worker = JudgeWorker(session_factory=test_session_factory, runner=FakeRunner())

    assert worker.run_once()

    with test_session_factory() as session:
        submission = session.get(Submission, submission_id)
        attempt = session.get(JudgeAttempt, attempt_id)
        assert submission.status == "COMPLETED"
        assert submission.authoritative_attempt_id == attempt_id
        assert attempt.verdict.verdict == "ACCEPTED"
        assert attempt.verdict.score == 100


def test_worker_retries_transient_judge_infrastructure_error(test_session_factory):
    submission_id, attempt_id = create_queued_submission(test_session_factory, "worker-retry")
    worker = JudgeWorker(
        session_factory=test_session_factory,
        runner=FakeRunner(fail_once=True),
        worker_id="retry-worker",
    )

    assert worker.run_once()
    with test_session_factory() as session:
        job = session.query(JudgeJob).filter_by(attempt_id=attempt_id).one()
        assert job.status == "QUEUED"
        job.available_at = datetime.now(UTC)
        session.commit()

    assert worker.run_once()
    with test_session_factory() as session:
        submission = session.get(Submission, submission_id)
        attempt = session.get(JudgeAttempt, attempt_id)
        assert submission.status == "COMPLETED"
        assert attempt.verdict.verdict == "ACCEPTED"


def test_worker_recovers_an_abandoned_job_after_lease_expiry(test_session_factory):
    submission_id, attempt_id = create_queued_submission(test_session_factory, "worker-crash")
    with test_session_factory() as session:
        job = session.query(JudgeJob).filter_by(attempt_id=attempt_id).one()
        job.status = "RUNNING"
        job.worker_id = "crashed-worker"
        job.locked_at = datetime.now(UTC) - timedelta(minutes=5)
        job.retry_count = 0
        session.get(Submission, submission_id).status = "RUNNING"
        session.get(JudgeAttempt, attempt_id).status = "RUNNING"
        session.commit()

    worker = JudgeWorker(
        session_factory=test_session_factory,
        runner=FakeRunner(),
        worker_id="replacement-worker",
    )
    assert worker.run_once()

    with test_session_factory() as session:
        job = session.query(JudgeJob).filter_by(attempt_id=attempt_id).one()
        submission = session.get(Submission, submission_id)
        attempt = session.get(JudgeAttempt, attempt_id)
        assert job.status == "COMPLETED"
        assert job.retry_count == 1
        assert submission.status == "COMPLETED"
        assert submission.authoritative_attempt_id == attempt_id
        assert attempt.verdict.verdict == "ACCEPTED"
