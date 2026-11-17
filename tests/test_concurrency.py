import multiprocessing
import os
from uuid import uuid4
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.models.contest import Contest
from app.models.judge_job import JudgeJob
from app.models.organization import Organization
from app.models.problem import Problem, ProblemVersion, TestSuite as SuiteModel
from app.models.submission import JudgeAttempt, Submission
from app.models.user import User
from app.workers.judge_worker import JudgeWorker


def _claim_job(database_url: str, worker_id: str, start, results) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    start.wait()
    result = JudgeWorker(session_factory=factory, worker_id=worker_id)._claim()
    results.put(result)
    engine.dispose()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to PostgreSQL for multi-process SKIP LOCKED test",
)
def test_two_worker_processes_do_not_claim_the_same_job():
    database_url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    suffix = str(uuid4())
    organization_id, user_id = str(uuid4()), str(uuid4())
    contest_id, problem_id = str(uuid4()), str(uuid4())
    version_id, suite_id = str(uuid4()), str(uuid4())
    submission_id, attempt_id = str(uuid4()), str(uuid4())
    job_id = str(uuid4())
    with factory() as session:
        organization = Organization(id=organization_id, name=f"Concurrency {suffix}")
        user = User(id=user_id, email=f"{suffix}@example.test", password_hash="unused")
        contest = Contest(
            id=contest_id,
            organization_id=organization_id,
            name="Concurrency test",
            start_time=datetime.now(UTC),
            end_time=datetime.now(UTC) + timedelta(hours=1),
        )
        problem = Problem(id=problem_id, organization_id=organization_id, title="Test")
        version = ProblemVersion(
            id=version_id, problem_id=problem_id, version=1, statement="Test"
        )
        suite = SuiteModel(id=suite_id, problem_version_id=version_id, suite_version=1)
        submission = Submission(
            id=submission_id,
            user_id=user_id,
            contest_id=contest_id,
            problem_version_id=version_id,
            suite_id=suite_id,
            code="print(1)",
            status="QUEUED",
            idempotency_key="parallel-claim",
            request_hash="parallel",
        )
        attempt = JudgeAttempt(
            id=attempt_id, submission_id=submission_id, attempt_number=1, status="QUEUED"
        )
        job = JudgeJob(
            id=job_id,
            submission_id=submission_id,
            attempt_id=attempt_id,
            status="QUEUED",
            available_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add_all(
            [organization, user]
        )
        session.flush()
        session.add_all([contest, problem])
        session.flush()
        session.add_all([version, suite])
        session.flush()
        session.add(submission)
        session.flush()
        session.add(attempt)
        session.flush()
        session.add(job)
        session.commit()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    workers = [
        context.Process(target=_claim_job, args=(database_url, f"worker-{i}", start, results))
        for i in range(2)
    ]
    for process in workers:
        process.start()
    start.set()
    claims = [results.get(timeout=15) for _ in workers]
    for process in workers:
        process.join(timeout=15)
        assert process.exitcode == 0

    claimed_ids = [claim[0] for claim in claims if claim is not None]
    assert len(claimed_ids) == 1
    with factory() as session:
        session.execute(delete(JudgeJob).where(JudgeJob.id == job_id))
        session.execute(delete(JudgeAttempt).where(JudgeAttempt.id == attempt_id))
        session.execute(delete(Submission).where(Submission.id == submission_id))
        session.execute(delete(SuiteModel).where(SuiteModel.id == suite_id))
        session.execute(delete(ProblemVersion).where(ProblemVersion.id == version_id))
        session.execute(delete(Problem).where(Problem.id == problem_id))
        session.execute(delete(Contest).where(Contest.id == contest_id))
        session.execute(delete(User).where(User.id == user_id))
        session.execute(delete(Organization).where(Organization.id == organization_id))
        session.commit()
    engine.dispose()
