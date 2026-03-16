from datetime import datetime
from uuid import uuid4

from app.core.constants import ProcessingStatus, Rating, TagSource, VariantType
from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


def generate_uuid() -> str:
    return str(uuid4())


class Image(TimestampMixin, Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    uuid_short: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type_original: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_original: Mapped[int] = mapped_column(nullable=False)
    file_size_stored: Mapped[int | None] = mapped_column(nullable=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    video_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aspect_ratio: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    storage_ext: Mapped[str] = mapped_column(String(16), default="png", nullable=False)
    rating: Mapped[Rating] = mapped_column(Enum(Rating, name="rating"), default=Rating.GENERAL, nullable=False)
    nsfw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status"),
        default=ProcessingStatus.PENDING,
        nullable=False,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nsfw_model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploaded_by = relationship("User", back_populates="uploads")
    variants = relationship("ImageVariant", back_populates="image", cascade="all, delete-orphan")
    tags = relationship("ImageTag", back_populates="image", cascade="all, delete-orphan")
    moderation = relationship("ImageModeration", back_populates="image", cascade="all, delete-orphan", uselist=False)
    reports = relationship("ImageReport", back_populates="image", cascade="all, delete-orphan")
    comments = relationship("ImageComment", back_populates="image", cascade="all, delete-orphan")


class ImageVariant(Base):
    __tablename__ = "image_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_type: Mapped[VariantType] = mapped_column(Enum(VariantType, name="variant_type"), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    image = relationship("Image", back_populates="variants")


class ImageTag(TimestampMixin, Base):
    __tablename__ = "image_tags"
    __table_args__ = (UniqueConstraint("image_id", "tag_id", "source"),)

    image_id: Mapped[str] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[TagSource] = mapped_column(Enum(TagSource, name="tag_source"), primary_key=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    image = relationship("Image", back_populates="tags")
    tag = relationship("Tag")
