from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    contest_id: Mapped[str] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), index=True)
    problem_version_id: Mapped[str] = mapped_column(
        ForeignKey("problem_versions.id"), nullable=False
    )
    suite_id: Mapped[str] = mapped_column(ForeignKey("test_suites.id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authoritative_attempt_id: Mapped[str | None] = mapped_column(
        ForeignKey("judge_attempts.id", use_alter=True, name="fk_submission_authoritative_attempt"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    attempts: Mapped[list["JudgeAttempt"]] = relationship(
        back_populates="submission", foreign_keys="JudgeAttempt.submission_id"
    )


class JudgeAttempt(Base):
    __tablename__ = "judge_attempts"
    __table_args__ = (UniqueConstraint("submission_id", "attempt_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submission: Mapped[Submission] = relationship(
        back_populates="attempts", foreign_keys=[submission_id]
    )
    verdict: Mapped["Verdict | None"] = relationship(back_populates="attempt", uselist=False)


class Verdict(Base):
    __tablename__ = "verdicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("judge_attempts.id", ondelete="CASCADE"), unique=True, index=True
    )
    verdict: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[JudgeAttempt] = relationship(back_populates="verdict")
