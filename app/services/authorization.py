from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contest import ContestParticipant
from app.models.organization import Membership


def is_contest_participant(db: Session, contest_id: str, user_id: str) -> bool:
    return (
        db.scalar(
            select(ContestParticipant.id).where(
                ContestParticipant.contest_id == contest_id,
                ContestParticipant.user_id == user_id,
            )
        )
        is not None
    )


def organization_role(db: Session, organization_id: str, user_id: str) -> str | None:
    membership = db.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
        )
    )
    return membership.role if membership else None
