from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Base
from app.models.contest import Contest, ContestParticipant
from app.models.organization import Membership, Organization
from app.models.problem import ContestProblem, Problem, ProblemVersion, TestCase, TestSuite
from app.models.user import User


@pytest.fixture
def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with TestingSession() as db:
        organization = Organization(id="org-one", name="One")
        other_organization = Organization(id="org-two", name="Two")
        organizer = User(
            id="user-organizer",
            email="organizer@example.com",
            password_hash=hash_password("organizer-password"),
        )
        participant = User(
            id="user-participant",
            email="participant@example.com",
            password_hash=hash_password("participant-password"),
        )
        outsider = User(
            id="user-outsider",
            email="outsider@example.com",
            password_hash=hash_password("outsider-password"),
        )
        contest = Contest(
            id="contest-one",
            organization_id=organization.id,
            name="Test Contest",
            start_time=datetime.now(UTC) - timedelta(minutes=5),
            end_time=datetime.now(UTC) + timedelta(hours=1),
        )
        problem = Problem(
            id="problem-one",
            organization_id=organization.id,
            title="Sum",
            current_version=1,
        )
        version = ProblemVersion(
            id="version-one",
            problem=problem,
            version=1,
            statement="Add two integers",
        )
        suite = TestSuite(id="suite-one", problem_version=version, suite_version=1)
        suite.cases.extend(
            [
                TestCase(input="1 2\n", expected_output="3\n", is_sample=True),
                TestCase(input="2 4\n", expected_output="6\n", is_sample=False),
            ]
        )
        contest.problems.append(
            ContestProblem(
                problem_version_id=version.id,
                suite_id=suite.id,
                points=100,
            )
        )
        db.add_all(
            [
                organization,
                other_organization,
                organizer,
                participant,
                outsider,
                Membership(user=organizer, organization=organization, role="organizer"),
                Membership(user=participant, organization=organization, role="participant"),
                Membership(user=outsider, organization=other_organization, role="participant"),
                contest,
                problem,
                version,
                suite,
                ContestParticipant(contest=contest, user=participant),
            ]
        )
        db.commit()

    yield TestingSession
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(test_session_factory):
    def override_get_db():
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
