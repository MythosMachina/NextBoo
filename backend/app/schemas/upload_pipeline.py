from datetime import datetime

from pydantic import BaseModel


class UploadPipelineStageCard(BaseModel):
    stage: str
    label: str
    workers: int
    queued: int
    running: int
    failed: int
    completed: int
    total: int
    media_images: int
    media_videos: int
    last_activity_at: str | None = None


class UploadPipelineLiveBatch(BaseModel):
    id: int
    submitted_by_username: str | None
    status: str
    total_items: int
    completed_items: int
    duplicate_items: int
    rejected_items: int
    failed_items: int
    updated_at: datetime


class UploadPipelineControlRoomRead(BaseModel):
    stages: list[UploadPipelineStageCard]
    active_batches: list[UploadPipelineLiveBatch]
    worker_image_count: int
    worker_video_count: int
    queue_image_depth: int
    queue_video_depth: int
    quarantined_items: int
    failed_items: int
    duplicate_items: int
    accepted_items: int
    last_refresh_at: str


class UploadPipelineControlRoomResponse(BaseModel):
    data: UploadPipelineControlRoomRead
    meta: dict[str, int | str | None] = {}
