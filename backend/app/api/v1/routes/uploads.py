import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from app.api.deps import DbSession, RedisClient
from app.core.constants import ImportSourceType, ImportStatus, JobStatus, JobType, UserRole
from app.models.image import Image
from app.models.import_job import ImportBatch, Job
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
from app.services.app_settings import ingest_queue_name_for_provider
from app.services.permissions import require_upload_access
from app.services.rate_limits import enforce_rate_limit
from app.services.storage import StorageService
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status

try:
    from app.services.app_settings import get_tagger_provider as resolve_tagger_provider
except ImportError:
    from app.services.app_settings import get_active_tagger_provider as resolve_tagger_provider


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


def create_import_batch(
    db: DbSession,
    current_user: User,
    *,
    source_type: ImportSourceType,
    source_name: str,
) -> ImportBatch:
    import_batch = ImportBatch(
        source_type=source_type,
        source_name=source_name,
        submitted_by_user_id=current_user.id,
        total_files=0,
        status=ImportStatus.PENDING,
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
    import_batch: ImportBatch | None = None
    rejections = list(rejected or [])
    tagger_provider = resolve_tagger_provider(db)
    ingest_queue_name = ingest_queue_name_for_provider(tagger_provider)

    if staged_uploads:
        incoming_hashes = [str(item["checksum_sha256"]) for item in staged_uploads]
        existing_rows = (
            db.query(Image.checksum_sha256, Image.id)
            .filter(Image.checksum_sha256.in_(incoming_hashes))
            .all()
        )
        existing_hash_map = {checksum: image_id for checksum, image_id in existing_rows}
        seen_batch_hashes: set[str] = set()
        unique_uploads: list[dict[str, str | int]] = []

        for item in staged_uploads:
            checksum_sha256 = str(item["checksum_sha256"])
            queue_path = Path(str(item["queue_path"]))
            duplicate_image_id = existing_hash_map.get(checksum_sha256)
            if duplicate_image_id:
                queue_path.unlink(missing_ok=True)
                rejections.append(
                    UploadRejectedItem(
                        client_key=str(item["client_key"]),
                        filename=str(item["filename"]),
                        error="Duplicate file already exists in the gallery.",
                    )
                )
                record_upload_outcome(
                    redis_client,
                    outcome="duplicate",
                    message=f"Duplicate upload matched existing image {duplicate_image_id}",
                    image_id=str(duplicate_image_id),
                )
                continue

            if checksum_sha256 in seen_batch_hashes:
                queue_path.unlink(missing_ok=True)
                rejections.append(
                    UploadRejectedItem(
                        client_key=str(item["client_key"]),
                        filename=str(item["filename"]),
                        error="Duplicate file inside the current import batch.",
                    )
                )
                record_upload_outcome(
                    redis_client,
                    outcome="duplicate",
                    message="Duplicate upload matched another file in the same import batch.",
                )
                continue

            seen_batch_hashes.add(checksum_sha256)
            unique_uploads.append(item)

        staged_uploads = unique_uploads

    for item in staged_uploads:
        if import_batch is None:
            import_batch = create_import_batch(
                db,
                current_user,
                source_type=source_type,
                source_name=source_name,
            )

        job = Job(
            job_type=JobType.INGEST,
            queue_path=str(item["queue_path"]),
            status=JobStatus.QUEUED,
            retry_count=0,
            max_retries=3,
            import_batch_id=import_batch.id,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        redis_client.rpush(ingest_queue_name, str(job.id))
        accepted.append(
            UploadAcceptedItem(
                client_key=str(item["client_key"]),
                filename=str(item["filename"]),
                job_id=job.id,
            )
        )

    if import_batch is not None:
        import_batch.total_files = len(accepted)
        import_batch.failed_files = len(rejections)
        import_batch.status = ImportStatus.RUNNING if accepted else ImportStatus.FAILED
        if not accepted:
            import_batch.finished_at = datetime.now(timezone.utc)
        db.add(import_batch)
        db.commit()

    return UploadResponse(
        data=accepted,
        rejected=rejections,
        meta={
            "count": len(accepted),
            "rejected_count": len(rejections),
            "import_id": import_batch.id if import_batch is not None else "",
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

        queue_path, checksum_sha256 = storage.write_upload_to_queue(upload)
        file_size = Path(queue_path).stat().st_size
        if file_size > MAX_FILE_SIZE:
            Path(queue_path).unlink(missing_ok=True)
            rejected.append(
                UploadRejectedItem(
                    client_key=client_key,
                    filename=upload.filename or Path(queue_path).name,
                    error="File exceeds maximum size.",
                )
            )
            continue

        staged_uploads.append(
            {
                "client_key": client_key,
                "filename": upload.filename or Path(queue_path).name,
                "queue_path": queue_path,
                "checksum_sha256": checksum_sha256,
                "file_size": file_size,
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
        queue_path, checksum_sha256 = storage.stage_local_file_to_queue(path)
        file_size = Path(queue_path).stat().st_size
        if file_size > MAX_FILE_SIZE:
            Path(queue_path).unlink(missing_ok=True)
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
                "queue_path": queue_path,
                "checksum_sha256": checksum_sha256,
                "file_size": file_size,
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
            queue_path, checksum_sha256 = storage.stage_local_file_to_queue(path)
            file_size = Path(queue_path).stat().st_size
            if file_size > MAX_FILE_SIZE:
                Path(queue_path).unlink(missing_ok=True)
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
                    "queue_path": queue_path,
                    "checksum_sha256": checksum_sha256,
                    "file_size": file_size,
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

    query = (
        db.query(Job)
        .join(ImportBatch, ImportBatch.id == Job.import_batch_id)
        .filter(Job.id.in_(requested_ids))
    )
    if current_user.role == UserRole.UPLOADER:
        query = query.filter(ImportBatch.submitted_by_user_id == current_user.id)

    jobs = query.all()
    return UploadStatusResponse(
        data=[
            UploadJobStatusItem(
                job_id=job.id,
                status=job.status.value,
                image_id=job.image_id,
                last_error=job.last_error,
            )
            for job in jobs
        ],
        meta={"count": len(jobs)},
    )
