from datetime import UTC, datetime, timedelta

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.contest import Contest, ContestParticipant
from app.models.organization import Membership, Organization
from app.models.problem import (
    ContestProblem,
    Problem,
    ProblemVersion,
    TestCase,
    TestSuite,
)
from app.models.user import User

SEED_IDS = {
    "organization": "00000000-0000-4000-8000-000000000001",
    "organizer": "00000000-0000-4000-8000-000000000002",
    "participant": "00000000-0000-4000-8000-000000000003",
    "contest": "00000000-0000-4000-8000-000000000004",
    "problem": "00000000-0000-4000-8000-000000000005",
    "problem_version": "00000000-0000-4000-8000-000000000006",
    "suite": "00000000-0000-4000-8000-000000000007",
}


def main() -> None:
    with SessionLocal() as db:
        organization = db.get(Organization, SEED_IDS["organization"])
        if organization is not None:
            print("Deterministic seed data already exists.")
            return

        organization = Organization(id=SEED_IDS["organization"], name="Shodh Demo")
        organizer = User(
            id=SEED_IDS["organizer"],
            email="organizer@example.com",
            password_hash=hash_password("ChangeMe-Organizer-123!"),
        )
        participant = User(
            id=SEED_IDS["participant"],
            email="participant@example.com",
            password_hash=hash_password("ChangeMe-Participant-123!"),
        )
        problem = Problem(
            id=SEED_IDS["problem"],
            organization_id=organization.id,
            title="Add two integers",
            current_version=1,
        )
        version = ProblemVersion(
            id=SEED_IDS["problem_version"],
            problem_id=problem.id,
            version=1,
            statement="Read two integers and print their sum.",
        )
        suite = TestSuite(
            id=SEED_IDS["suite"],
            problem_version_id=version.id,
            suite_version=1,
        )
        suite.cases.extend(
            [
                TestCase(input="2 3\n", expected_output="5\n", is_sample=True),
                TestCase(input="-4 10\n", expected_output="6\n", is_sample=False),
            ]
        )
        contest = Contest(
            id=SEED_IDS["contest"],
            organization_id=organization.id,
            name="Demo Contest",
            start_time=datetime.now(UTC) - timedelta(hours=1),
            end_time=datetime.now(UTC) + timedelta(days=1),
        )
        contest.problems.append(
            ContestProblem(
                problem_version_id=version.id,
                suite_id=suite.id,
                points=100,
            )
        )
        db.add_all([organization, organizer, participant])
        db.flush()
        db.add_all(
            [
                Membership(user=organizer, organization=organization, role="organizer"),
                Membership(user=participant, organization=organization, role="participant"),
                problem,
            ]
        )
        db.flush()
        db.add(version)
        db.flush()
        db.add(suite)
        db.flush()
        db.add(contest)
        db.flush()
        db.add(ContestParticipant(contest=contest, user=participant))
        db.commit()
        print("Seeded Shodh Demo organization, contest, users, and problem.")
        print("Demo passwords are documented in README.md; change them before deployment.")


if __name__ == "__main__":
    main()
