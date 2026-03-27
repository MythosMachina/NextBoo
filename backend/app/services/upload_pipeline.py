from __future__ import annotations

import os
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.constants import JobStatus, UploadPipelineBatchStatus, UploadPipelineItemStatus, UploadPipelineStage
from app.models.import_job import Job
from app.models.upload_pipeline import UploadPipelineBatch, UploadPipelineItem
from app.models.user import User
from app.services.operations import sanitize_jobs_and_imports
from app.services.storage_sanitation import sanitize_gallery_storage
from redis import Redis
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session


STAGE_LABELS = {
    "ingress": "Ingress",
    "quarantine": "Quarantine",
    "scanning": "Scanning",
    "dedupe": "Dedupe",
    "normalize": "Normalize",
    "dispatch": "Dispatch",
    "final_ingest": "Final Ingest",
}

STAGE_ORDER = [
    "quarantine",
    "scanning",
    "dedupe",
    "normalize",
    "dispatch",
    "final_ingest",
]


def _safe_remove_path(path: str | None) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        return


def _reconcile_batch_counters(db: Session, batch_id: int) -> None:
    batch = db.get(UploadPipelineBatch, batch_id)
    if batch is None:
        return

    rows = (
        db.query(
            UploadPipelineItem.status.label("status"),
            func.count(UploadPipelineItem.id).label("count"),
        )
        .filter(UploadPipelineItem.batch_id == batch_id)
        .group_by(UploadPipelineItem.status)
        .all()
    )
    counts = {str(row.status): int(row.count or 0) for row in rows}

    completed = counts.get(UploadPipelineItemStatus.COMPLETED, 0)
    duplicate = counts.get(UploadPipelineItemStatus.DUPLICATE, 0)
    rejected = counts.get(UploadPipelineItemStatus.REJECTED, 0)
    failed = counts.get(UploadPipelineItemStatus.FAILED, 0)
    queued = counts.get(UploadPipelineItemStatus.QUEUED, 0)
    running = counts.get(UploadPipelineItemStatus.RUNNING, 0)
    received = counts.get(UploadPipelineItemStatus.RECEIVED, 0)

    batch.completed_items = completed
    batch.duplicate_items = duplicate
    batch.rejected_items = rejected
    batch.failed_items = failed
    batch.total_items = completed + duplicate + rejected + failed + queued + running + received

    if queued or running or received:
        batch.status = UploadPipelineBatchStatus.RUNNING
        batch.finished_at = None
    elif failed > 0:
        batch.status = UploadPipelineBatchStatus.FAILED
        batch.finished_at = datetime.now(timezone.utc)
    else:
        batch.status = UploadPipelineBatchStatus.COMPLETED
        batch.finished_at = datetime.now(timezone.utc)


def acknowledge_failed_items(db: Session) -> int:
    failed_items = (
        db.query(UploadPipelineItem)
        .filter(UploadPipelineItem.status == UploadPipelineItemStatus.FAILED)
        .all()
    )
    if not failed_items:
        return 0

    affected_batch_ids = {item.batch_id for item in failed_items}
    removed = 0
    for item in failed_items:
        _safe_remove_path(item.quarantine_path)
        _safe_remove_path(item.normalized_path)
        db.delete(item)
        removed += 1

    db.flush()
    for batch_id in affected_batch_ids:
        _reconcile_batch_counters(db, batch_id)
    db.commit()
    return removed


def acknowledge_failed_final_ingest_jobs(db: Session) -> int:
    settings = get_settings()
    failed_jobs = db.query(Job).filter(Job.status == JobStatus.FAILED).all()
    if not failed_jobs:
        return 0

    removed = 0
    for job in failed_jobs:
        queue_name = os.path.basename(job.queue_path)
        if queue_name:
            _safe_remove_path(job.queue_path)
            _safe_remove_path(os.path.join(settings.processing_failed_path, queue_name))
        db.delete(job)
        removed += 1

    sanitize_jobs_and_imports(db)
    sanitize_gallery_storage(db)
    db.commit()
    return removed

def build_control_room_snapshot(db: Session, redis_client: Redis) -> dict[str, object]:
    stage_worker_counts = {
        stage: len(redis_client.keys(f"nextboo:upload-stage:{stage}:*"))
        for stage in ("scanning", "dedupe", "normalize", "dispatch")
    }
    stage_rows = (
        db.query(
            UploadPipelineItem.stage.label("stage"),
            func.count(UploadPipelineItem.id).label("total"),
            func.sum(case((UploadPipelineItem.status == UploadPipelineItemStatus.QUEUED, 1), else_=0)).label("queued"),
            func.sum(case((UploadPipelineItem.status == UploadPipelineItemStatus.RUNNING, 1), else_=0)).label("running"),
            func.sum(case((UploadPipelineItem.status == UploadPipelineItemStatus.FAILED, 1), else_=0)).label("failed"),
            func.sum(
                case(
                    (
                        UploadPipelineItem.status.in_(
                            [
                                UploadPipelineItemStatus.COMPLETED,
                                UploadPipelineItemStatus.DUPLICATE,
                                UploadPipelineItemStatus.REJECTED,
                            ]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("completed"),
            func.sum(case((UploadPipelineItem.media_family == "image", 1), else_=0)).label("media_images"),
            func.sum(case((UploadPipelineItem.media_family == "video", 1), else_=0)).label("media_videos"),
            func.max(UploadPipelineItem.last_stage_change_at).label("last_activity_at"),
        )
        .group_by(UploadPipelineItem.stage)
        .all()
    )

    stage_map = {str(row.stage): row for row in stage_rows}
    final_ingest_row = (
        db.query(
            func.sum(case((Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]), 1), else_=0)).label("queued"),
            func.sum(case((Job.status == JobStatus.RUNNING, 1), else_=0)).label("running"),
            func.sum(case((Job.status == JobStatus.FAILED, 1), else_=0)).label("failed"),
            func.sum(case((Job.status == JobStatus.DONE, 1), else_=0)).label("completed"),
            func.count(Job.id).label("total"),
            func.max(Job.updated_at).label("last_activity_at"),
        )
        .first()
    )

    stage_cards: list[dict[str, object]] = []
    for stage in STAGE_ORDER:
        if stage == "final_ingest":
            stage_cards.append(
                {
                    "stage": stage,
                    "label": STAGE_LABELS[stage],
                    "workers": 0,
                    "queued": int(final_ingest_row.queued or 0),
                    "running": int(final_ingest_row.running or 0),
                    "failed": int(final_ingest_row.failed or 0),
                    "completed": int(final_ingest_row.completed or 0),
                    "total": int(final_ingest_row.total or 0),
                    "media_images": 0,
                    "media_videos": 0,
                    "last_activity_at": final_ingest_row.last_activity_at.isoformat() if final_ingest_row.last_activity_at else None,
                }
            )
            continue
        row = stage_map.get(stage)
        stage_cards.append(
            {
                "stage": stage,
                "label": STAGE_LABELS[stage],
                "workers": int(stage_worker_counts.get(stage, 0)),
                "queued": int((row.queued if row else 0) or 0),
                "running": int((row.running if row else 0) or 0),
                "failed": int((row.failed if row else 0) or 0),
                "completed": int((row.completed if row else 0) or 0),
                "total": int((row.total if row else 0) or 0),
                "media_images": int((row.media_images if row else 0) or 0),
                "media_videos": int((row.media_videos if row else 0) or 0),
                "last_activity_at": row.last_activity_at.isoformat() if row and row.last_activity_at else None,
            }
        )

    active_batches_rows = (
        db.query(UploadPipelineBatch, User.username)
        .outerjoin(User, User.id == UploadPipelineBatch.submitted_by_user_id)
        .filter(
            UploadPipelineBatch.status.in_(
                [
                    UploadPipelineBatchStatus.RECEIVED,
                    UploadPipelineBatchStatus.RUNNING,
                    UploadPipelineBatchStatus.PAUSED,
                    UploadPipelineBatchStatus.FAILED,
                ]
            )
        )
        .order_by(desc(UploadPipelineBatch.updated_at))
        .limit(12)
        .all()
    )
    active_batches = [
        {
            "id": batch.id,
            "submitted_by_username": username,
            "status": str(batch.status),
            "total_items": batch.total_items,
            "completed_items": batch.completed_items,
            "duplicate_items": batch.duplicate_items,
            "rejected_items": batch.rejected_items,
            "failed_items": batch.failed_items,
            "updated_at": batch.updated_at,
        }
        for batch, username in active_batches_rows
    ]

    active_worker_ids = sorted(
        key.removeprefix("nextboo:workers:active:")
        for key in redis_client.keys("nextboo:workers:active:*")
    )
    active_image_worker_ids = sorted(
        key.removeprefix("nextboo:workers:image:active:")
        for key in redis_client.keys("nextboo:workers:image:active:*")
    )
    active_video_worker_ids = sorted(
        key.removeprefix("nextboo:workers:video:active:")
        for key in redis_client.keys("nextboo:workers:video:active:*")
    )
    queue_image_depth = int(redis_client.llen("jobs:ingest:camie"))
    queue_video_depth = int(redis_client.llen("jobs:ingest:video"))

    quarantined_items = (
        db.query(func.count(UploadPipelineItem.id))
        .filter(
            UploadPipelineItem.stage == UploadPipelineStage.QUARANTINE,
            UploadPipelineItem.status.in_(
                [
                    UploadPipelineItemStatus.RECEIVED,
                    UploadPipelineItemStatus.QUEUED,
                    UploadPipelineItemStatus.RUNNING,
                ]
            ),
        )
        .scalar()
        or 0
    )
    failed_items = db.query(func.count(UploadPipelineItem.id)).filter(UploadPipelineItem.status == UploadPipelineItemStatus.FAILED).scalar() or 0
    duplicate_items = db.query(func.count(UploadPipelineItem.id)).filter(UploadPipelineItem.status == UploadPipelineItemStatus.DUPLICATE).scalar() or 0
    accepted_items = db.query(func.count(UploadPipelineItem.id)).filter(UploadPipelineItem.status == UploadPipelineItemStatus.COMPLETED).scalar() or 0

    return {
        "stages": stage_cards,
        "active_batches": active_batches,
        "worker_image_count": len(active_image_worker_ids) or len(active_worker_ids),
        "worker_video_count": len(active_video_worker_ids),
        "queue_image_depth": queue_image_depth,
        "queue_video_depth": queue_video_depth,
        "quarantined_items": int(quarantined_items),
        "failed_items": int(failed_items),
        "duplicate_items": int(duplicate_items),
        "accepted_items": int(accepted_items),
        "last_refresh_at": datetime.now(timezone.utc).isoformat(),
    }
