from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class BoardImportRun(TimestampMixin, Base):
    __tablename__ = "board_import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    board_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tag_query: Mapped[str] = mapped_column(Text, nullable=False)
    requested_limit: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    discovered_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    downloaded_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queued_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_posts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BoardImportEvent(Base):
    __tablename__ = "board_import_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("board_import_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), default="log", nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    remote_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
