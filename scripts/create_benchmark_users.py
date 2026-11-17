import argparse
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.contest import Contest, ContestParticipant
from app.models.organization import Membership, Organization
from app.models.user import User

ORGANIZATION_ID = "00000000-0000-4000-8000-000000000001"
CONTEST_ID = "00000000-0000-4000-8000-000000000004"
PASSWORD = "ChangeMe-Benchmark-123!"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local-only deterministic load-test users")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")

    with SessionLocal() as db:
        organization = db.get(Organization, ORGANIZATION_ID)
        contest = db.get(Contest, CONTEST_ID)
        if organization is None or contest is None:
            raise SystemExit("Run `python -m scripts.seed` before creating benchmark users.")

        for index in range(1, args.count + 1):
            email = f"loadtest-{index:04d}@loadtest.example.com"
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=str(uuid5(NAMESPACE_URL, f"shodh-contest/{email}")),
                    email=email,
                    password_hash=hash_password(PASSWORD),
                )
                db.add(user)
                db.flush()

            membership = db.scalar(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.organization_id == organization.id,
                )
            )
            if membership is None:
                db.add(
                    Membership(
                        user_id=user.id,
                        organization_id=organization.id,
                        role="participant",
                    )
                )
            participant = db.scalar(
                select(ContestParticipant.id).where(
                    ContestParticipant.contest_id == contest.id,
                    ContestParticipant.user_id == user.id,
                )
            )
            if participant is None:
                db.add(
                    ContestParticipant(
                        contest_id=contest.id,
                        user_id=user.id,
                    )
                )

        db.commit()
    print(f"Created or verified {args.count} benchmark participants.")
    print(f"Local-only password for all benchmark accounts: {PASSWORD}")


if __name__ == "__main__":
    main()
