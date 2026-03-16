from datetime import datetime

from app.core.constants import Rating, ReportReason, ReportStatus, VisibilityStatus
from pydantic import BaseModel


class ImageReportCreate(BaseModel):
    reason: ReportReason
    message: str | None = None


class ImageMetadataUpdate(BaseModel):
    tag_names: list[str] | None = None
    add_tag_names: list[str] | None = None
    remove_tag_names: list[str] | None = None
    rating: Rating | None = None


class ImageVisibilityUpdate(BaseModel):
    visibility_status: VisibilityStatus
    reason: str | None = None
    note: str | None = None


class ReportReviewUpdate(BaseModel):
    status: ReportStatus
    review_note: str | None = None


class ModerationReportRead(BaseModel):
    id: int
    image_id: str
    image_uuid_short: str
    image_rating: Rating
    image_visibility_status: VisibilityStatus
    reported_by_username: str | None
    reason: ReportReason
    message: str | None
    status: ReportStatus
    review_note: str | None
    reviewed_by_username: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ModerationReportsEnvelope(BaseModel):
    data: list[ModerationReportRead]
    meta: dict[str, int | str | None] = {}


class ModerationImageRead(BaseModel):
    id: str
    uuid_short: str
    original_filename: str
    rating: Rating
    visibility_status: VisibilityStatus
    uploaded_by_username: str | None
    report_count_open: int
    created_at: datetime


class ModerationImagesEnvelope(BaseModel):
    data: list[ModerationImageRead]
    meta: dict[str, int | str | None] = {}


class ModerationCommentRead(BaseModel):
    id: int
    image_id: str
    image_uuid_short: str
    image_rating: Rating
    body: str
    score: int
    is_flagged: bool
    author_username: str | None
    created_at: datetime
    updated_at: datetime


class ModerationCommentsEnvelope(BaseModel):
    data: list[ModerationCommentRead]
    meta: dict[str, int | str | None] = {}


class ModerationNearDuplicateRead(BaseModel):
    id: int
    image_id: str
    similar_image_id: str
    image_uuid_short: str
    similar_image_uuid_short: str
    hamming_distance: int
    status: str
    created_at: datetime
    updated_at: datetime


class ModerationNearDuplicatesEnvelope(BaseModel):
    data: list[ModerationNearDuplicateRead]
    meta: dict[str, int | str | None] = {}
