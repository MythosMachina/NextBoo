from datetime import datetime

from app.core.constants import ImportStatus, JobStatus, JobType
from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_type: JobType
    image_id: str | None
    queue_path: str
    status: JobStatus
    retry_count: int
    max_retries: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class JobsResponse(BaseModel):
    data: list[JobRead]
    meta: dict[str, int | str]


class JobOutcomeRead(BaseModel):
    job_id: int | None
    import_batch_id: int | None
    outcome: str
    message: str | None
    image_id: str | None
    created_at: datetime


class JobOverviewResponse(BaseModel):
    data: dict[str, int | str | list[JobOutcomeRead] | list[str] | dict[str, int] | None]
    meta: dict[str, int | str]


class ImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    status: ImportStatus
    total_files: int
    processed_files: int
    failed_files: int
    created_at: datetime
    updated_at: datetime


class ImportsResponse(BaseModel):
    data: list[ImportRead]
    meta: dict[str, int | str]
