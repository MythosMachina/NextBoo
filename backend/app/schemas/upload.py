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


class ImportFolderRequest(BaseModel):
    folder_name: str


class ImportZipRequest(BaseModel):
    zip_name: str


class ImportSourceListing(BaseModel):
    folders: list[str]
    zip_archives: list[str]


class ImportSourceResponse(BaseModel):
    data: ImportSourceListing
    meta: dict[str, int | str]
