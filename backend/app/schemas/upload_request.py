from datetime import datetime

from app.core.constants import UploadRequestStatus
from pydantic import BaseModel


class UploadRequestCreate(BaseModel):
    content_focus: str
    reason: str


class UploadRequestReview(BaseModel):
    status: UploadRequestStatus
    review_note: str | None = None


class UploadRequestRead(BaseModel):
    id: int
    username: str
    user_id: int
    content_focus: str
    reason: str
    status: UploadRequestStatus
    review_note: str | None
    reviewed_by_username: str | None
    created_at: datetime
    reviewed_at: datetime | None


class UploadRequestEnvelope(BaseModel):
    data: list[UploadRequestRead]
    meta: dict[str, int | str | None] = {}
