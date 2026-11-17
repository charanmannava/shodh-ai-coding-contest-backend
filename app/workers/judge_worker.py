import argparse
import logging
import os
import socket
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.models.judge_job import JudgeJob
from app.models.problem import TestCase
from app.models.submission import JudgeAttempt, Submission, Verdict
from app.sandbox.docker_runner import DockerRunner
from app.services.judging import JudgeResult, judge_submission

logger = logging.getLogger(__name__)


class JudgeWorker:
    def __init__(
        self,
        session_factory=SessionLocal,
        runner: DockerRunner | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.runner = runner or DockerRunner()
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.settings = get_settings()

    def run_once(self) -> bool:
        claimed = self._claim()
        if claimed is None:
            return False
        job_id, submission_id, attempt_id = claimed
        logger.info(
            "Claimed judge job",
            extra={"submission_id": submission_id, "attempt_id": attempt_id},
        )
        with self.session_factory() as session:
            submission = session.get(Submission, submission_id)
            attempt = session.get(JudgeAttempt, attempt_id)
            cases = list(
                session.scalars(
                    select(TestCase)
                    .where(TestCase.suite_id == submission.suite_id)
                    .order_by(TestCase.id)
                )
            )
            code = submission.code
            test_inputs = [(case.input, case.expected_output) for case in cases]
        result = judge_submission(code, test_inputs, self.runner)
        self._finish(job_id, submission_id, attempt_id, result)
        return True

    def _claim(self) -> tuple[str, str, str] | None:
        now = datetime.now(UTC)
        lease_expires = now - timedelta(seconds=self.settings.judge_lease_seconds)
        with self.session_factory() as session:
            job = session.scalar(
                select(JudgeJob)
                .where(
                    or_(
                        (JudgeJob.status == "QUEUED") & (JudgeJob.available_at <= now),
                        (JudgeJob.status == "RUNNING") & (JudgeJob.locked_at < lease_expires),
                    )
                )
                .order_by(JudgeJob.available_at, JudgeJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None

            if job.status == "RUNNING":
                if job.retry_count >= self.settings.judge_max_attempts:
                    self._complete_in_session(
                        session,
                        job,
                        "JUDGE_ERROR",
                        0,
                        "Worker lease expired too many times",
                    )
                    session.commit()
                    return None
                job.retry_count += 1
            job.status = "RUNNING"
            job.worker_id = self.worker_id
            job.locked_at = now
            attempt = session.get(JudgeAttempt, job.attempt_id)
            attempt.status = "RUNNING"
            submission = session.get(Submission, job.submission_id)
            if self._is_latest_attempt(session, submission, attempt):
                submission.status = "RUNNING"
            session.commit()
            return job.id, job.submission_id, job.attempt_id

    def _finish(
        self, job_id: str, submission_id: str, attempt_id: str, result: JudgeResult
    ) -> None:
        with self.session_factory() as session:
            job = session.scalar(
                select(JudgeJob).where(JudgeJob.id == job_id).with_for_update()
            )
            if job is None or job.status != "RUNNING" or job.worker_id != self.worker_id:
                logger.warning(
                    "Discarding result from expired worker lease",
                    extra={"submission_id": submission_id, "attempt_id": attempt_id},
                )
                return
            submission = session.scalar(
                select(Submission)
                .where(Submission.id == submission_id)
                .with_for_update()
            )
            if result.verdict == "JUDGE_ERROR" and job.retry_count < self.settings.judge_max_attempts:
                job.retry_count += 1
                job.status = "QUEUED"
                job.available_at = datetime.now(UTC) + timedelta(
                    seconds=min(2**job.retry_count, 30)
                )
                job.worker_id = None
                job.locked_at = None
                attempt = session.get(JudgeAttempt, attempt_id)
                attempt.status = "QUEUED"
                if self._is_latest_attempt(session, submission, attempt):
                    submission.status = "QUEUED"
                session.commit()
                logger.error(
                    "Judge infrastructure failure; retry scheduled",
                    extra={"submission_id": submission_id, "attempt_id": attempt_id},
                )
                return
            self._complete_in_session(
                session,
                job,
                result.verdict,
                result.score,
                result.details,
            )
            session.commit()
        logger.info(
            "Judge job completed",
            extra={"submission_id": submission_id, "attempt_id": attempt_id},
        )

    def _complete_in_session(
        self,
        session: Session,
        job: JudgeJob,
        verdict_name: str,
        score: int,
        details: str,
    ) -> None:
        now = datetime.now(UTC)
        job.status = "COMPLETED"
        job.locked_at = None
        job.worker_id = None
        attempt = session.get(JudgeAttempt, job.attempt_id)
        attempt.status = "COMPLETED"
        attempt.completed_at = now
        session.add(
            Verdict(
                attempt_id=attempt.id,
                verdict=verdict_name,
                score=score,
                details=details[:4000],
            )
        )
        submission = session.scalar(
            select(Submission)
            .where(Submission.id == job.submission_id)
            .with_for_update()
        )
        current_authoritative = (
            session.get(JudgeAttempt, submission.authoritative_attempt_id)
            if submission.authoritative_attempt_id
            else None
        )
        if current_authoritative is None or attempt.attempt_number > current_authoritative.attempt_number:
            submission.authoritative_attempt_id = attempt.id
            submission.status = "COMPLETED"

    @staticmethod
    def _is_latest_attempt(
        session: Session, submission: Submission, attempt: JudgeAttempt
    ) -> bool:
        latest = session.scalar(
            select(JudgeAttempt.attempt_number)
            .where(JudgeAttempt.submission_id == submission.id)
            .order_by(JudgeAttempt.attempt_number.desc())
            .limit(1)
        )
        return latest == attempt.attempt_number


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll and process contest judge jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    worker = JudgeWorker()
    if args.once:
        worker.run_once()
        return
    while True:
        if not worker.run_once():
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
