from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BoardImportBoardItem(BaseModel):
    name: str
    family: str
    site_url: str


class BoardImportBoardsResponse(BaseModel):
    data: list[BoardImportBoardItem]
    meta: dict[str, int | str] = {}


class BoardImportRunCreate(BaseModel):
    board_name: str = Field(default="", max_length=255)
    tags: str = Field(min_length=1, max_length=2000)
    requested_limit: int = Field(default=25, ge=1, le=250)
    all_boards: bool = False


class BoardImportEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    event_type: str
    message: str
    remote_post_id: str | None = None
    job_id: int | None = None
    image_id: str | None = None
    is_error: bool
    created_at: datetime


class BoardImportRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_name: str
    tag_query: str
    requested_limit: int
    hourly_limit: int
    status: str
    discovered_posts: int
    downloaded_posts: int
    queued_posts: int
    completed_posts: int
    duplicate_posts: int
    skipped_posts: int
    failed_posts: int
    current_message: str | None = None
    error_summary: str | None = None
    source_import_batch_id: int | None = None
    submitted_by_user_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_event_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BoardImportRunDetailRead(BoardImportRunRead):
    events: list[BoardImportEventRead] = []


class BoardImportRunResponse(BaseModel):
    data: BoardImportRunDetailRead
    meta: dict[str, int | str] = {}


class BoardImportRunsResponse(BaseModel):
    data: list[BoardImportRunRead]
    meta: dict[str, int | str] = {}
