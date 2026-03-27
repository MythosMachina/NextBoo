from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class UploadPipelineBatch(TimestampMixin, Base):
    __tablename__ = "upload_pipeline_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    linked_import_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="web")
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False, index=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadPipelineItem(TimestampMixin, Base):
    __tablename__ = "upload_pipeline_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("upload_pipeline_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    client_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    detected_mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    media_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quarantine_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    normalized_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default="ingress", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False, index=True)
    detail_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_import_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True, index=True)
    linked_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    linked_image_id: Mapped[str | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"), nullable=True, index=True)
    last_stage_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
