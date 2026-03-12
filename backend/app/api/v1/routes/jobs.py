from pathlib import Path
from typing import Annotated

from app.api.deps import DbSession, RedisClient, require_roles
from app.core.config import get_settings
from app.core.constants import JobStatus, UserRole
from app.models.import_job import ImportBatch, Job
from app.models.image import Image
from app.models.user import User
from app.schemas.job import ImportRead, ImportsResponse, JobOutcomeRead, JobOverviewResponse, JobRead, JobsResponse
from app.services.app_settings import ingest_queue_name_for_provider
from app.services.operations import sanitize_jobs_and_imports
from app.services.storage_sanitation import sanitize_gallery_storage
from fastapi import APIRouter, Depends
from sqlalchemy import func

try:
    from app.services.app_settings import get_tagger_provider as resolve_tagger_provider
except ImportError:
    from app.services.app_settings import get_active_tagger_provider as resolve_tagger_provider


OUTCOME_STREAM_KEY = "nextboo:jobs:outcomes"
OUTCOME_STREAM_LIMIT = 500
DEFAULT_PAGE_SIZE = 100


router = APIRouter(prefix="/jobs")


@router.get("", response_model=JobsResponse)
def list_jobs(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    page: int = 1,
    limit: int = DEFAULT_PAGE_SIZE,
) -> JobsResponse:
    sanitize_jobs_and_imports(db)
    db.commit()
    safe_limit = max(1, min(limit, 500))
    safe_page = max(1, page)
    total_count = db.query(func.count(Job.id)).scalar() or 0
    jobs = (
        db.query(Job)
        .order_by(Job.created_at.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
        .all()
    )
    total_pages = max(1, (total_count + safe_limit - 1) // safe_limit) if total_count else 1
    return JobsResponse(
        data=[JobRead.model_validate(job) for job in jobs],
        meta={"count": len(jobs), "page": safe_page, "limit": safe_limit, "total_count": int(total_count), "total_pages": total_pages},
    )


@router.get("/imports", response_model=ImportsResponse)
def list_imports(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR, UserRole.UPLOADER))],
    page: int = 1,
    limit: int = DEFAULT_PAGE_SIZE,
) -> ImportsResponse:
    sanitize_jobs_and_imports(db)
    db.commit()
    safe_limit = max(1, min(limit, 500))
    safe_page = max(1, page)
    total_count = db.query(func.count(ImportBatch.id)).scalar() or 0
    imports = (
        db.query(ImportBatch)
        .order_by(ImportBatch.created_at.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
        .all()
    )
    total_pages = max(1, (total_count + safe_limit - 1) // safe_limit) if total_count else 1
    return ImportsResponse(
        data=[ImportRead.model_validate(item) for item in imports],
        meta={"count": len(imports), "page": safe_page, "limit": safe_limit, "total_count": int(total_count), "total_pages": total_pages},
    )


@router.get("/overview", response_model=JobOverviewResponse)
def jobs_overview(
    db: DbSession,
    redis_client: RedisClient,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> JobOverviewResponse:
    sanitize_jobs_and_imports(db)
    db.commit()

    queue_counts = {status.value: 0 for status in JobStatus}
    for status, count in db.query(Job.status, func.count(Job.id)).group_by(Job.status).all():
        queue_counts[status.value] = int(count)

    recent_raw = redis_client.lrange(OUTCOME_STREAM_KEY, 0, 99)
    recent_outcomes: list[JobOutcomeRead] = []
    outcome_counts = {"accepted": 0, "duplicate": 0, "failed": 0}

    for raw_item in recent_raw:
        payload = JobOutcomeRead.model_validate_json(raw_item)
        recent_outcomes.append(payload)
        if payload.outcome == "accepted":
            outcome_counts["accepted"] += 1
        elif payload.outcome == "duplicate":
            outcome_counts["duplicate"] += 1
        else:
            outcome_counts["failed"] += 1

    displayed_total = db.query(func.count(Image.id)).scalar() or 0

    return JobOverviewResponse(
        data={
            "queue": queue_counts,
            "displayed_total": int(displayed_total),
            "recent_counts": outcome_counts,
            "recent_outcomes": recent_outcomes,
            "tracked_outcomes": len(recent_outcomes),
        },
        meta={"count": len(recent_outcomes), "stream_limit": OUTCOME_STREAM_LIMIT},
    )


@router.post("/{job_id}/requeue")
def requeue_job(
    job_id: int,
    db: DbSession,
    redis_client: RedisClient,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    job = db.get(Job, job_id)
    if not job:
        return {"data": None, "meta": {"status": "missing"}}
    if job.status not in {JobStatus.FAILED, JobStatus.RETRYING, JobStatus.QUEUED}:
        return {"data": {"job_id": job.id}, "meta": {"status": "ignored", "reason": f"status={job.status.value}"}}
    job.status = JobStatus.QUEUED
    job.last_error = None
    job.locked_at = None
    job.locked_by = None
    db.add(job)
    db.commit()
    redis_client.rpush(ingest_queue_name_for_provider(resolve_tagger_provider(db)), str(job.id))
    return {"data": {"job_id": job.id}, "meta": {"status": "queued"}}


@router.post("/{job_id}/dismiss")
def dismiss_failed_job(
    job_id: int,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    job = db.get(Job, job_id)
    if not job:
        return {"data": None, "meta": {"status": "missing"}}
    if job.status != JobStatus.FAILED:
        return {"data": {"job_id": job.id}, "meta": {"status": "ignored", "reason": f"status={job.status.value}"}}

    settings = get_settings()
    queue_path = Path(job.queue_path)
    processing_failed_path = Path(settings.processing_failed_path) / queue_path.name
    for candidate in (queue_path, processing_failed_path):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            continue

    db.delete(job)
    sanitize_jobs_and_imports(db)
    sanitize_gallery_storage(db)
    db.commit()
    return {"data": {"job_id": job_id}, "meta": {"status": "dismissed"}}
