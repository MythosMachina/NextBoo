from datetime import datetime

from app.core.constants import AliasType, Rating, TagCategory
from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Tag(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_normalized: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[TagCategory] = mapped_column(
        Enum(TagCategory, name="tag_category"),
        default=TagCategory.GENERAL,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    aliases = relationship("TagAlias", back_populates="target_tag")
    rating_rule = relationship("TagRatingRule", back_populates="tag", cascade="all, delete-orphan", uselist=False)


class TagAlias(TimestampMixin, Base):
    __tablename__ = "tag_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    target_tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    alias_type: Mapped[AliasType] = mapped_column(
        Enum(AliasType, name="alias_type"),
        default=AliasType.SYNONYM,
        nullable=False,
    )

    target_tag = relationship("Tag", back_populates="aliases")


class TagMerge(Base):
    __tablename__ = "tag_merges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    target_tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    merged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    merged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TagRatingRule(TimestampMixin, Base):
    __tablename__ = "tag_rating_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    target_rating: Mapped[Rating] = mapped_column(
        Enum(Rating, name="rating_rule_target"),
        nullable=False,
    )
    boost: Mapped[float] = mapped_column(default=0.2, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tag = relationship("Tag", back_populates="rating_rule")
