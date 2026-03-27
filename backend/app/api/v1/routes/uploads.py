import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from app.api.deps import DbSession, RedisClient
from app.core.constants import ImportSourceType, JobStatus, UploadPipelineBatchStatus, UploadPipelineItemStatus, UploadPipelineStage, UserRole
from app.models.import_job import ImportBatch, Job
from app.models.upload_pipeline import UploadPipelineBatch, UploadPipelineItem
from app.models.user import User
from app.schemas.upload import (
    ImportFolderRequest,
    ImportSourceListing,
    ImportSourceResponse,
    ImportZipRequest,
    UploadAcceptedItem,
    UploadJobStatusItem,
    UploadRejectedItem,
    UploadResponse,
    UploadStatusResponse,
)
from app.services.permissions import require_upload_access
from app.services.rate_limits import enforce_rate_limit
from app.services.storage import StorageService
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status

router = APIRouter(prefix="/uploads")

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/gif",
    "video/webm",
    "video/mp4",
    "video/x-matroska",
}
MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_FILES_PER_REQUEST = 100
OUTCOME_STREAM_KEY = "nextboo:jobs:outcomes"
OUTCOME_STREAM_LIMIT = 500
ZIP_STAGING_PREFIX = "zip_"
UPLOAD_SCAN_QUEUE = "upload:stage:scan"


def record_upload_outcome(
    redis_client: RedisClient,
    *,
    outcome: str,
    message: str,
    import_batch_id: int | None = None,
    image_id: str | None = None,
) -> None:
    payload = json.dumps(
        {
            "job_id": None,
            "import_batch_id": import_batch_id,
            "outcome": outcome,
            "message": message,
            "image_id": image_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    redis_client.lpush(OUTCOME_STREAM_KEY, payload)
    redis_client.ltrim(OUTCOME_STREAM_KEY, 0, OUTCOME_STREAM_LIMIT - 1)


def detect_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def create_upload_pipeline_batch(
    db: DbSession,
    current_user: User,
    *,
    source_name: str,
) -> UploadPipelineBatch:
    import_batch = UploadPipelineBatch(
        source_name=source_name,
        submitted_by_user_id=current_user.id,
        total_items=0,
        status=UploadPipelineBatchStatus.RECEIVED.value,
    )
    db.add(import_batch)
    db.commit()
    db.refresh(import_batch)
    return import_batch


def finalize_staged_uploads(
    db: DbSession,
    redis_client: RedisClient,
    current_user: User,
    staged_uploads: list[dict[str, str | int]],
    *,
    source_type: ImportSourceType,
    source_name: str,
    rejected: list[UploadRejectedItem] | None = None,
) -> UploadResponse:
    accepted: list[UploadAcceptedItem] = []
    pipeline_batch: UploadPipelineBatch | None = None
    rejections = list(rejected or [])

    for item in staged_uploads:
        if pipeline_batch is None:
            pipeline_batch = create_upload_pipeline_batch(
                db,
                current_user,
                source_name=source_name,
            )

        pipeline_item = UploadPipelineItem(
            batch_id=pipeline_batch.id,
            submitted_by_user_id=current_user.id,
            client_key=str(item["client_key"]),
            original_filename=str(item["filename"]),
            detected_mime_type=str(item["mime_type"]),
            quarantine_path=str(item["quarantine_path"]),
            checksum_sha256=str(item["checksum_sha256"]),
            source_size=int(item["file_size"]),
            stage=UploadPipelineStage.QUARANTINE.value,
            status=UploadPipelineItemStatus.QUEUED.value,
            detail_message="Queued for quarantine scan.",
        )
        db.add(pipeline_item)
        db.commit()
        db.refresh(pipeline_item)
        redis_client.rpush(UPLOAD_SCAN_QUEUE, str(pipeline_item.id))
        accepted.append(
            UploadAcceptedItem(
                client_key=str(item["client_key"]),
                filename=str(item["filename"]),
                upload_item_id=pipeline_item.id,
                job_id=None,
            )
        )

    if pipeline_batch is not None:
        pipeline_batch.total_items = len(accepted) + len(rejections)
        pipeline_batch.rejected_items = len(rejections)
        pipeline_batch.status = UploadPipelineBatchStatus.RUNNING.value if accepted else UploadPipelineBatchStatus.FAILED.value
        if not accepted:
            pipeline_batch.finished_at = datetime.now(timezone.utc)
        db.add(pipeline_batch)
        db.commit()

    return UploadResponse(
        data=accepted,
        rejected=rejections,
        meta={
            "count": len(accepted),
            "rejected_count": len(rejections),
            "import_id": "",
            "pipeline_batch_id": pipeline_batch.id if pipeline_batch is not None else "",
            "source_type": source_type.value,
        },
    )


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_files(
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_upload_access)],
    files: Annotated[list[UploadFile], File(...)],
    client_keys: Annotated[list[str], Form()] = [],
) -> UploadResponse:
    enforce_rate_limit(db, redis_client, request, "upload", current_user=current_user)
    if len(files) > MAX_FILES_PER_REQUEST:
        return UploadResponse(
            data=[],
            rejected=[
                UploadRejectedItem(
                    client_key="batch",
                    filename="batch",
                    error=f"Too many files in request. Maximum is {MAX_FILES_PER_REQUEST}.",
                )
            ],
            meta={"count": 0, "rejected_count": 1},
        )

    storage = StorageService()
    rejected: list[UploadRejectedItem] = []
    staged_uploads: list[dict[str, str | int]] = []

    for index, upload in enumerate(files):
        client_key = client_keys[index] if index < len(client_keys) else (upload.filename or "unknown")
        if upload.content_type not in ALLOWED_MIME_TYPES:
            rejected.append(
                UploadRejectedItem(
                    client_key=client_key,
                    filename=upload.filename or "unknown",
                    error=f"Unsupported MIME type: {upload.content_type}",
                )
            )
            continue

        quarantine_path, checksum_sha256 = storage.write_upload_to_quarantine(upload)
        file_size = Path(quarantine_path).stat().st_size
        if file_size > MAX_FILE_SIZE:
            Path(quarantine_path).unlink(missing_ok=True)
            rejected.append(
                UploadRejectedItem(
                    client_key=client_key,
                    filename=upload.filename or Path(quarantine_path).name,
                    error="File exceeds maximum size.",
                )
            )
            continue

        staged_uploads.append(
            {
                "client_key": client_key,
                "filename": upload.filename or Path(quarantine_path).name,
                "quarantine_path": quarantine_path,
                "checksum_sha256": checksum_sha256,
                "file_size": file_size,
                "mime_type": upload.content_type or detect_content_type(upload.filename or "upload.bin"),
            }
        )

    return finalize_staged_uploads(
        db,
        redis_client,
        current_user,
        staged_uploads,
        source_type=ImportSourceType.WEB,
        source_name=f"web-upload-{datetime.now(timezone.utc).isoformat()}",
        rejected=rejected,
    )


@router.get("/import-sources", response_model=ImportSourceResponse)
def list_import_sources(
    current_user: Annotated[User, Depends(require_upload_access)],
) -> ImportSourceResponse:
    storage = StorageService()
    sources = storage.list_import_sources()
    return ImportSourceResponse(
        data=ImportSourceListing(**sources),
        meta={"folder_count": len(sources["folders"]), "zip_count": len(sources["zip_archives"])},
    )


@router.post("/import-folder", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def import_from_folder(
    payload: ImportFolderRequest,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_upload_access)],
) -> UploadResponse:
    enforce_rate_limit(db, redis_client, request, "upload", current_user=current_user)
    storage = StorageService()
    base_import_path = storage.import_path.resolve()
    folder_name = Path(payload.folder_name).name
    source_folder = (base_import_path / folder_name).resolve()
    if base_import_path not in source_folder.parents and source_folder != base_import_path:
        return UploadResponse(
            data=[],
            rejected=[UploadRejectedItem(client_key=folder_name, filename=folder_name, error="Folder path is invalid.")],
            meta={"count": 0, "rejected_count": 1, "source_type": ImportSourceType.FOLDER.value},
        )
    if not source_folder.exists() or not source_folder.is_dir():
        return UploadResponse(
            data=[],
            rejected=[UploadRejectedItem(client_key=folder_name, filename=folder_name, error="Folder does not exist.")],
            meta={"count": 0, "rejected_count": 1, "source_type": ImportSourceType.FOLDER.value},
        )

    staged_uploads: list[dict[str, str | int]] = []
    rejected: list[UploadRejectedItem] = []
    for path in storage.iter_importable_files(source_folder)[:MAX_FILES_PER_REQUEST]:
        quarantine_path, checksum_sha256 = storage.stage_local_file_to_quarantine(path)
        file_size = Path(quarantine_path).stat().st_size
        if file_size > MAX_FILE_SIZE:
            Path(quarantine_path).unlink(missing_ok=True)
            rejected.append(
                UploadRejectedItem(
                    client_key=str(path.relative_to(source_folder)),
                    filename=path.name,
                    error="File exceeds maximum size.",
                )
            )
            continue
        staged_uploads.append(
            {
                "client_key": str(path.relative_to(source_folder)),
                "filename": path.name,
                "quarantine_path": quarantine_path,
                "checksum_sha256": checksum_sha256,
                "file_size": file_size,
                "mime_type": detect_content_type(path.name),
            }
        )

    return finalize_staged_uploads(
        db,
        redis_client,
        current_user,
        staged_uploads,
        source_type=ImportSourceType.FOLDER,
        source_name=folder_name,
        rejected=rejected,
    )


@router.post("/import-zip", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def import_from_zip(
    payload: ImportZipRequest,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_upload_access)],
) -> UploadResponse:
    enforce_rate_limit(db, redis_client, request, "upload", current_user=current_user)
    storage = StorageService()
    base_import_path = storage.import_path.resolve()
    zip_name = Path(payload.zip_name).name
    zip_path = (base_import_path / zip_name).resolve()
    if base_import_path not in zip_path.parents and zip_path != base_import_path:
        return UploadResponse(
            data=[],
            rejected=[UploadRejectedItem(client_key=zip_name, filename=zip_name, error="ZIP path is invalid.")],
            meta={"count": 0, "rejected_count": 1, "source_type": ImportSourceType.ZIP.value},
        )
    if not zip_path.exists() or not zip_path.is_file() or zip_path.suffix.lower() != ".zip":
        return UploadResponse(
            data=[],
            rejected=[UploadRejectedItem(client_key=zip_name, filename=zip_name, error="ZIP archive does not exist.")],
            meta={"count": 0, "rejected_count": 1, "source_type": ImportSourceType.ZIP.value},
        )

    staging_root = storage.import_path / f"{ZIP_STAGING_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{zip_path.stem}"
    extracted_files = storage.safe_extract_zip(zip_path, staging_root)
    staged_uploads: list[dict[str, str | int]] = []
    rejected: list[UploadRejectedItem] = []
    try:
        for path in extracted_files[:MAX_FILES_PER_REQUEST]:
            if detect_content_type(path.name) not in ALLOWED_MIME_TYPES:
                continue
            quarantine_path, checksum_sha256 = storage.stage_local_file_to_quarantine(path)
            file_size = Path(quarantine_path).stat().st_size
            if file_size > MAX_FILE_SIZE:
                Path(quarantine_path).unlink(missing_ok=True)
                rejected.append(
                    UploadRejectedItem(
                        client_key=str(path.relative_to(staging_root)),
                        filename=path.name,
                        error="File exceeds maximum size.",
                    )
                )
                continue
            staged_uploads.append(
                {
                    "client_key": str(path.relative_to(staging_root)),
                    "filename": path.name,
                    "quarantine_path": quarantine_path,
                    "checksum_sha256": checksum_sha256,
                    "file_size": file_size,
                    "mime_type": detect_content_type(path.name),
                }
            )

        return finalize_staged_uploads(
            db,
            redis_client,
            current_user,
            staged_uploads,
            source_type=ImportSourceType.ZIP,
            source_name=zip_name,
            rejected=rejected,
        )
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


@router.get("/status", response_model=UploadStatusResponse)
def get_upload_status(
    db: DbSession,
    current_user: Annotated[User, Depends(require_upload_access)],
    job_ids: str = Query(default=""),
) -> UploadStatusResponse:
    requested_ids = [int(item) for item in job_ids.split(",") if item.strip().isdigit()]
    if not requested_ids:
        return UploadStatusResponse(data=[], meta={"count": 0})

    item_query = db.query(UploadPipelineItem).filter(UploadPipelineItem.id.in_(requested_ids))
    if current_user.role == UserRole.UPLOADER:
        item_query = item_query.filter(UploadPipelineItem.submitted_by_user_id == current_user.id)

    items = item_query.all()
    linked_job_ids = [item.linked_job_id for item in items if item.linked_job_id]
    jobs_by_id: dict[int, Job] = {}
    if linked_job_ids:
        job_query = (
            db.query(Job)
            .join(ImportBatch, ImportBatch.id == Job.import_batch_id)
            .filter(Job.id.in_(linked_job_ids))
        )
        if current_user.role == UserRole.UPLOADER:
            job_query = job_query.filter(ImportBatch.submitted_by_user_id == current_user.id)
        jobs_by_id = {job.id: job for job in job_query.all()}

    return UploadStatusResponse(
        data=[
            UploadJobStatusItem(
                upload_item_id=item.id,
                job_id=item.linked_job_id or 0,
                status=(
                    jobs_by_id[item.linked_job_id].status.value
                    if item.linked_job_id in jobs_by_id
                    else item.status
                ),
                image_id=item.linked_image_id or (jobs_by_id[item.linked_job_id].image_id if item.linked_job_id in jobs_by_id else None),
                last_error=(
                    jobs_by_id[item.linked_job_id].last_error
                    if item.linked_job_id in jobs_by_id
                    else item.detail_message
                ),
            )
            for item in items
        ],
        meta={"count": len(items)},
    )
