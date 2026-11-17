from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JudgeJob(Base):
    __tablename__ = "judge_jobs"
    __table_args__ = (
        Index(
            "ix_judge_jobs_queued_available",
            "available_at",
            "id",
            postgresql_where=text("status = 'QUEUED'"),
        ),
        Index(
            "ix_judge_jobs_stale_lease",
            "locked_at",
            "available_at",
            "id",
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("judge_attempts.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
