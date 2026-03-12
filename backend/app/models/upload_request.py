from datetime import datetime

from app.core.constants import UploadRequestStatus
from app.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class UploadPermissionRequest(TimestampMixin, Base):
    __tablename__ = "upload_permission_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_focus: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[UploadRequestStatus] = mapped_column(
        Enum(
            UploadRequestStatus,
            name="upload_request_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=UploadRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
