from datetime import datetime

from app.core.constants import ProcessingStatus, Rating, TagCategory, TagSource, VariantType, VisibilityStatus
from app.schemas.comment import ImageCommentRead
from pydantic import BaseModel, ConfigDict


class TagItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_normalized: str
    display_name: str
    category: TagCategory


class UploaderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class ImageTagItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tag: TagItem
    confidence: float | None
    source: TagSource
    is_manual: bool
    rating_cue: str | None = None


class ImageVariantItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_type: VariantType
    relative_path: str
    mime_type: str
    width: int
    height: int
    file_size: int
    url: str | None = None


class ImageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    uuid_short: str
    original_filename: str
    width: int
    height: int
    duration_seconds: float | None = None
    frame_rate: float | None = None
    has_audio: bool = False
    video_codec: str | None = None
    audio_codec: str | None = None
    rating: Rating
    processing_status: ProcessingStatus
    created_at: datetime
    uploaded_by: UploaderItem | None = None
    visibility_status: VisibilityStatus = VisibilityStatus.VISIBLE
    thumb_url: str | None = None
    preview_url: str | None = None
    preview_mime_type: str | None = None
    vote_score: int = 0


class ImageDetail(ImageListItem):
    variants: list[ImageVariantItem]
    tags: list[ImageTagItem]
    comments: list[ImageCommentRead] = []
    can_edit: bool = False
    can_delete: bool = False
    can_moderate: bool = False
    manual_tag_names: list[str] = []
    current_user_vote: int | None = None
    vote_cooldown_remaining_seconds: int = 0


class ImageListResponse(BaseModel):
    data: list[ImageListItem]
    meta: dict[str, int | str | None]
    next_cursor: str | None = None


class ImageDetailResponse(BaseModel):
    data: ImageDetail
    meta: dict[str, str] = {}
