from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_membership
from app.core.database import get_db
from app.models.contest import Contest, ContestParticipant
from app.models.organization import Membership
from app.models.problem import (
    ContestProblem,
    Problem,
    ProblemVersion,
    TestCase,
    TestSuite,
)
from app.models.user import User
from app.schemas import ProblemCreate, ProblemResponse

router = APIRouter(prefix="/problems", tags=["problems"])


@router.post("", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED)
def create_problem(
    payload: ProblemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProblemResponse:
    require_membership(db, user.id, payload.organization_id, {"organizer", "admin"})
    problem = Problem(
        organization_id=payload.organization_id,
        title=payload.title,
        current_version=1,
    )
    version = ProblemVersion(version=1, statement=payload.statement)
    suite = TestSuite(suite_version=1)
    suite.cases.extend(
        TestCase(
            input=case.input,
            expected_output=case.expected_output,
            is_sample=case.is_sample,
        )
        for case in payload.test_cases
    )
    version.suites.append(suite)
    problem.versions.append(version)
    db.add(problem)
    db.commit()
    db.refresh(problem)
    return ProblemResponse(
        id=problem.id,
        title=problem.title,
        version=version.version,
        statement=version.statement,
        samples=[
            {"input": case.input, "expected_output": case.expected_output}
            for case in suite.cases
            if case.is_sample
        ],
    )


@router.get("/{problem_id}", response_model=ProblemResponse)
def get_problem(
    problem_id: str,
    contest_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProblemResponse:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
    member = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == problem.organization_id,
        )
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
    if contest_id is None:
        eligible_contests = select(Contest.id).where(
            Contest.organization_id == problem.organization_id
        )
        if member.role == "participant":
            eligible_contests = eligible_contests.join(
                ContestParticipant, ContestParticipant.contest_id == Contest.id
            ).where(ContestParticipant.user_id == user.id)
        contest_id = db.scalar(eligible_contests.order_by(Contest.start_time.desc()).limit(1))
    contest = db.get(Contest, contest_id) if contest_id else None
    if contest is None or contest.organization_id != problem.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
    if member.role == "participant" and db.scalar(
        select(ContestParticipant.id).where(
            ContestParticipant.contest_id == contest.id,
            ContestParticipant.user_id == user.id,
        )
    ) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Join the contest to view problems")
    contest_problem = db.scalar(
        select(ContestProblem).where(
            ContestProblem.contest_id == contest.id,
            ContestProblem.problem_version_id.in_(
                select(ProblemVersion.id).where(ProblemVersion.problem_id == problem.id)
            ),
        )
    )
    if contest_problem is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
    version = db.get(ProblemVersion, contest_problem.problem_version_id)
    suite = db.get(TestSuite, contest_problem.suite_id)
    samples = list(
        db.scalars(
            select(TestCase).where(TestCase.suite_id == suite.id, TestCase.is_sample.is_(True))
        )
    )
    return ProblemResponse(
        id=problem.id,
        title=problem.title,
        version=version.version,
        statement=version.statement,
        samples=[{"input": case.input, "expected_output": case.expected_output} for case in samples],
    )
