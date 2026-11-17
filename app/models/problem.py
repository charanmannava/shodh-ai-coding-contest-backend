from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    versions: Mapped[list["ProblemVersion"]] = relationship(back_populates="problem")


class ProblemVersion(Base):
    __tablename__ = "problem_versions"
    __table_args__ = (UniqueConstraint("problem_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    problem: Mapped[Problem] = relationship(back_populates="versions")
    suites: Mapped[list["TestSuite"]] = relationship(back_populates="problem_version")


class TestSuite(Base):
    __tablename__ = "test_suites"
    __table_args__ = (UniqueConstraint("problem_version_id", "suite_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    problem_version_id: Mapped[str] = mapped_column(
        ForeignKey("problem_versions.id", ondelete="CASCADE"), index=True
    )
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    problem_version: Mapped[ProblemVersion] = relationship(back_populates="suites")
    cases: Mapped[list["TestCase"]] = relationship(back_populates="suite")


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    suite_id: Mapped[str] = mapped_column(ForeignKey("test_suites.id", ondelete="CASCADE"), index=True)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suite: Mapped[TestSuite] = relationship(back_populates="cases")


class ContestProblem(Base):
    __tablename__ = "contest_problems"
    __table_args__ = (UniqueConstraint("contest_id", "problem_version_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    contest_id: Mapped[str] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    problem_version_id: Mapped[str] = mapped_column(
        ForeignKey("problem_versions.id", ondelete="CASCADE"), index=True
    )
    suite_id: Mapped[str] = mapped_column(ForeignKey("test_suites.id"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    contest: Mapped["Contest"] = relationship(back_populates="problems")
