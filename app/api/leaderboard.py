from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_membership
from app.core.database import get_db
from app.models.contest import Contest, ContestParticipant
from app.models.problem import ContestProblem
from app.models.submission import JudgeAttempt, Submission
from app.models.user import User
from app.schemas import LeaderboardEntry

router = APIRouter(prefix="/contests", tags=["leaderboard"])


@router.get("/{contest_id}/leaderboard", response_model=list[LeaderboardEntry])
def leaderboard(
    contest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LeaderboardEntry]:
    contest = db.get(Contest, contest_id)
    if contest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contest not found")
    require_membership(db, user.id, contest.organization_id)

    assignments = list(
        db.scalars(select(ContestProblem).where(ContestProblem.contest_id == contest.id))
    )
    weights = {item.problem_version_id: item.points for item in assignments}
    totals: dict[str, int] = defaultdict(int)
    latest_accepted: dict[str, datetime] = {}
    best: dict[tuple[str, str], int] = {}
    participants = list(
        db.scalars(
            select(ContestParticipant.user_id).where(
                ContestParticipant.contest_id == contest.id
            )
        )
    )

    completed = db.execute(
        select(Submission, JudgeAttempt)
        .join(JudgeAttempt, Submission.authoritative_attempt_id == JudgeAttempt.id)
        .where(Submission.contest_id == contest.id, JudgeAttempt.status == "COMPLETED")
    ).all()
    for submission, attempt in completed:
        verdict = attempt.verdict
        if verdict is None:
            continue
        key = (submission.user_id, submission.problem_version_id)
        weighted_score = verdict.score * weights.get(submission.problem_version_id, 0) // 100
        best[key] = max(best[key], weighted_score)
        if verdict.verdict == "ACCEPTED" and attempt.completed_at is not None:
            previous = latest_accepted.get(submission.user_id)
            if previous is None or attempt.completed_at > previous:
                latest_accepted[submission.user_id] = attempt.completed_at

    for (user_id, _), score in best.items():
        totals[user_id] += score
    ordered = sorted(
        participants,
        key=lambda user_id: (
            -totals[user_id],
            latest_accepted.get(user_id) or datetime.max.replace(tzinfo=UTC),
            user_id,
        ),
    )
    return [
        LeaderboardEntry(
            rank=index,
            user_id=user_id,
            score=totals[user_id],
            last_accepted_at=latest_accepted.get(user_id),
        )
        for index, user_id in enumerate(ordered, start=1)
    ]
