import hashlib
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_membership
from app.core.database import get_db
from app.core.time import as_utc
from app.models.contest import Contest, ContestParticipant
from app.models.judge_job import JudgeJob
from app.models.organization import Membership
from app.models.problem import ContestProblem, ProblemVersion
from app.models.submission import JudgeAttempt, Submission
from app.models.user import User
from app.schemas import SubmissionAccepted, SubmissionCreate, SubmissionResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/submissions", tags=["submissions"])


def _request_hash(payload: SubmissionCreate) -> str:
    raw = "\0".join((payload.contest_id, payload.problem_id, payload.code))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _submission_response(
    db: Session, submission: Submission, organizer: bool = False
) -> SubmissionResponse:
    verdict = None
    score = None
    attempts_payload = None
    if submission.authoritative_attempt_id:
        authoritative = db.get(JudgeAttempt, submission.authoritative_attempt_id)
        if authoritative and authoritative.verdict:
            verdict = authoritative.verdict.verdict
            score = authoritative.verdict.score
    if organizer:
        attempts = list(
            db.scalars(
                select(JudgeAttempt)
                .where(JudgeAttempt.submission_id == submission.id)
                .order_by(JudgeAttempt.attempt_number)
            )
        )
        attempts_payload = [
            {
                "attempt_number": attempt.attempt_number,
                "status": attempt.status,
                "verdict": attempt.verdict.verdict if attempt.verdict else None,
                "score": attempt.verdict.score if attempt.verdict else None,
                "details": attempt.verdict.details if attempt.verdict else None,
            }
            for attempt in attempts
        ]
    return SubmissionResponse(
        submission_id=submission.id,
        status=submission.status,
        verdict=verdict,
        score=score,
        message="Submission received" if submission.status == "QUEUED" else None,
        attempts=attempts_payload,
    )


@router.post("", response_model=SubmissionAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_submission(
    payload: SubmissionCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmissionAccepted:
    request_hash = _request_hash(payload)
    contest = db.get(Contest, payload.contest_id)
    if contest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contest not found")
    require_membership(db, user.id, contest.organization_id, {"participant"})
    participant = db.scalar(
        select(ContestParticipant.id).where(
            ContestParticipant.contest_id == contest.id,
            ContestParticipant.user_id == user.id,
        )
    )
    if participant is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Join the contest before submitting")
    existing = db.scalar(
        select(Submission).where(
            Submission.user_id == user.id,
            Submission.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency key reused with different request")
        return SubmissionAccepted(
            submission_id=existing.id, status=existing.status, message="Submission already received"
        )
    now = datetime.now(UTC)
    if now < as_utc(contest.start_time) or now > as_utc(contest.end_time):
        raise HTTPException(status.HTTP_409_CONFLICT, "Contest is not accepting submissions")
    problem_version = db.scalar(
        select(ProblemVersion)
        .join(ContestProblem, ContestProblem.problem_version_id == ProblemVersion.id)
        .where(
            ContestProblem.contest_id == contest.id,
            ProblemVersion.problem_id == payload.problem_id,
        )
    )
    if problem_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem is not part of this contest")
    assignment = db.scalar(
        select(ContestProblem).where(
            ContestProblem.contest_id == contest.id,
            ContestProblem.problem_version_id == problem_version.id,
        )
    )
    attempt = JudgeAttempt(attempt_number=1, status="QUEUED")
    submission = Submission(
        user_id=user.id,
        contest_id=contest.id,
        problem_version_id=problem_version.id,
        suite_id=assignment.suite_id,
        code=payload.code,
        status="QUEUED",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    submission.attempts.append(attempt)
    db.add(submission)
    db.flush()
    db.add(
        JudgeJob(
            submission_id=submission.id,
            attempt_id=attempt.id,
            status="QUEUED",
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Submission).where(
                Submission.user_id == user.id,
                Submission.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.request_hash != request_hash:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Idempotency key reused with different request"
            )
        return SubmissionAccepted(
            submission_id=existing.id, status=existing.status, message="Submission already received"
        )
    logger.info(
        "Submission queued",
        extra={"submission_id": submission.id, "attempt_id": attempt.id},
    )
    return SubmissionAccepted(
        submission_id=submission.id, status="QUEUED", message="Submission received"
    )


@router.get("/{submission_id}", response_model=SubmissionResponse)
def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmissionResponse:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    contest = db.get(Contest, submission.contest_id)
    role = db.scalar(
        select(Membership.role).where(
            Membership.user_id == user.id,
            Membership.organization_id == contest.organization_id,
        )
    )
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    if submission.user_id == user.id:
        return _submission_response(db, submission)
    if role not in {"organizer", "admin"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    return _submission_response(db, submission, organizer=True)


@router.post("/{submission_id}/rejudge", response_model=SubmissionAccepted, status_code=202)
def rejudge_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmissionAccepted:
    submission = db.scalar(
        select(Submission).where(Submission.id == submission_id).with_for_update()
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    contest = db.get(Contest, submission.contest_id)
    require_membership(db, user.id, contest.organization_id, {"organizer", "admin"})
    latest_number = db.scalar(
        select(JudgeAttempt.attempt_number)
        .where(JudgeAttempt.submission_id == submission.id)
        .order_by(JudgeAttempt.attempt_number.desc())
        .limit(1)
    ) or 0
    attempt = JudgeAttempt(
        submission_id=submission.id,
        attempt_number=latest_number + 1,
        status="QUEUED",
    )
    db.add(attempt)
    db.flush()
    db.add(JudgeJob(submission_id=submission.id, attempt_id=attempt.id, status="QUEUED"))
    submission.status = "QUEUED"
    db.commit()
    logger.info(
        "Submission rejudge queued",
        extra={"submission_id": submission.id, "attempt_id": attempt.id},
    )
    return SubmissionAccepted(
        submission_id=submission.id, status="QUEUED", message="Rejudge queued"
    )
