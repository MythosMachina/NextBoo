from pydantic import BaseModel


class UploadAcceptedItem(BaseModel):
    client_key: str
    filename: str
    job_id: int


class UploadRejectedItem(BaseModel):
    client_key: str
    filename: str
    error: str


class UploadResponse(BaseModel):
    data: list[UploadAcceptedItem]
    rejected: list[UploadRejectedItem]
    meta: dict[str, int | str]


class UploadJobStatusItem(BaseModel):
    job_id: int
    status: str
    image_id: str | None
    last_error: str | None


class UploadStatusResponse(BaseModel):
    data: list[UploadJobStatusItem]
    meta: dict[str, int | str]
