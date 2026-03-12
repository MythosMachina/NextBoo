from datetime import datetime

from app.core.constants import UserRole
from app.models.base import Base, TimestampMixin
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.UPLOADER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_upload: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invite_quota: Mapped[int] = mapped_column(default=2, nullable=False)
    can_view_questionable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_view_explicit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tag_blacklist: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploads = relationship("Image", back_populates="uploaded_by")
    invited_by = relationship("User", remote_side=[id], back_populates="invitees", foreign_keys=[invited_by_user_id])
    invitees = relationship("User", back_populates="invited_by", foreign_keys=[invited_by_user_id])
    sent_invites = relationship("UserInvite", back_populates="inviter", foreign_keys="UserInvite.inviter_user_id")
    received_strikes = relationship("UserStrike", back_populates="target_user", foreign_keys="UserStrike.target_user_id")
    issued_strikes = relationship("UserStrike", back_populates="issued_by_user", foreign_keys="UserStrike.issued_by_user_id")
    related_strikes = relationship("UserStrike", back_populates="related_user", foreign_keys="UserStrike.related_user_id")


class BannedEmail(TimestampMixin, Base):
    __tablename__ = "banned_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    banned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
