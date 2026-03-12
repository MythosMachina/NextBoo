from datetime import datetime

from app.core.constants import InviteStatus, StrikeSourceType, UserRole
from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class UserInvite(TimestampMixin, Base):
    __tablename__ = "user_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InviteStatus] = mapped_column(Enum(InviteStatus, name="invite_status"), nullable=False, default=InviteStatus.PENDING)
    inviter_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    invited_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    granted_role: Mapped[UserRole | None] = mapped_column(Enum(UserRole, name="user_role"), nullable=True)
    grant_can_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    grant_can_view_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    grant_invite_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rehabilitated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rehabilitated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    inviter = relationship("User", back_populates="sent_invites", foreign_keys=[inviter_user_id])
    invited_user = relationship("User", foreign_keys=[invited_user_id])
    rehabilitated_by = relationship("User", foreign_keys=[rehabilitated_by_user_id])


class UserStrike(TimestampMixin, Base):
    __tablename__ = "user_strikes"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    issued_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    related_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[StrikeSourceType] = mapped_column(
        Enum(StrikeSourceType, name="strike_source_type"),
        nullable=False,
        default=StrikeSourceType.MANUAL,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    target_user = relationship("User", back_populates="received_strikes", foreign_keys=[target_user_id])
    issued_by_user = relationship("User", back_populates="issued_strikes", foreign_keys=[issued_by_user_id])
    related_user = relationship("User", back_populates="related_strikes", foreign_keys=[related_user_id])
