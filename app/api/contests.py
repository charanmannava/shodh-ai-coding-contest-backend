from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_membership
from app.core.database import get_db
from app.core.time import as_utc
from app.models.contest import Contest, ContestParticipant
from app.models.organization import Membership
from app.models.problem import ContestProblem, Problem, ProblemVersion, TestSuite
from app.models.user import User
from app.schemas import ContestCreate, ContestResponse

router = APIRouter(prefix="/contests", tags=["contests"])


@router.get("", response_model=list[ContestResponse])
def list_contests(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Contest]:
    organizations = select(Membership.organization_id).where(Membership.user_id == user.id)
    return list(
        db.scalars(
            select(Contest)
            .where(Contest.organization_id.in_(organizations))
            .order_by(Contest.start_time)
        )
    )


@router.post("", response_model=ContestResponse, status_code=status.HTTP_201_CREATED)
def create_contest(
    payload: ContestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Contest:
    require_membership(db, user.id, payload.organization_id, {"organizer", "admin"})
    contest = Contest(
        organization_id=payload.organization_id,
        name=payload.name,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    for problem_id in payload.problem_ids:
        problem = db.scalar(
            select(Problem).where(
                Problem.id == problem_id,
                Problem.organization_id == payload.organization_id,
            )
        )
        if problem is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
        version = db.scalar(
            select(ProblemVersion).where(
                ProblemVersion.problem_id == problem.id,
                ProblemVersion.version == problem.current_version,
            )
        )
        suite = db.scalar(
            select(TestSuite).where(TestSuite.problem_version_id == version.id)
        ) if version else None
        if version is None or suite is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Problem has no active test suite")
        contest.problems.append(
            ContestProblem(problem_version_id=version.id, suite_id=suite.id)
        )
    db.add(contest)
    db.commit()
    db.refresh(contest)
    return contest


@router.post("/{contest_id}/join", status_code=status.HTTP_200_OK)
def join_contest(
    contest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    contest = db.get(Contest, contest_id)
    if contest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contest not found")
    membership = require_membership(db, user.id, contest.organization_id)
    if membership.role not in {"participant", "organizer", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient organization permissions")
    now = datetime.now(UTC)
    if now >= as_utc(contest.start_time):
        raise HTTPException(status.HTTP_409_CONFLICT, "Contest registration has closed")
    existing = db.scalar(
        select(ContestParticipant).where(
            ContestParticipant.contest_id == contest.id,
            ContestParticipant.user_id == user.id,
        )
    )
    if existing is None:
        db.add(ContestParticipant(contest_id=contest.id, user_id=user.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"contest_id": contest.id, "status": "JOINED"}
