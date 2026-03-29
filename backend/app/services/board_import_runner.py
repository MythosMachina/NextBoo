from __future__ import annotations

import logging
import json
import mimetypes
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.api.v1.routes.uploads import finalize_staged_uploads
from app.core.constants import ImportSourceType, JobStatus, Rating, TagCategory, TagSource, UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal, get_redis_client
from app.models.board_import import BoardImportEvent, BoardImportRun
from app.models.image import Image, ImageTag
from app.models.import_job import ImportBatch, Job
from app.models.tag import Tag
from app.models.upload_pipeline import UploadPipelineBatch, UploadPipelineItem
from app.models.user import User
from app.services.board_import.adapters import build_adapter
from app.services.board_import.importer import download_remote_post, parse_csv_tags
from app.services.board_import.presets import PRESETS, get_preset
from app.services.rating_rules import load_rating_rule_map, reclassify_image_from_rules
from app.services.storage import StorageService
from sqlalchemy.orm import Session, selectinload


logger = logging.getLogger("board_import_runner")

BOARD_IMPORT_QUEUE = "nextboo:board-import:queue"
OUTCOME_STREAM_KEY = "nextboo:jobs:outcomes"
OUTCOME_SCAN_LIMIT = 2000
BOARD_IMPORT_HOURLY_LIMIT = 1000
BOARD_IMPORT_JOB_TIMEOUT_SECONDS = 1800
BOARD_IMPORT_POLL_SECONDS = 3
BOROOUPLOADER_USERNAME = "boroouploader"
BOROOUPLOADER_PASSWORD = "BorooUploader123"


def supported_boards() -> list[dict[str, str]]:
    return [
        {"name": preset.name, "family": preset.family, "site_url": preset.site_url}
        for _key, preset in sorted(PRESETS.items(), key=lambda item: item[1].name.lower())
    ]


def ensure_boroo_uploader_user(db: Session) -> User:
    user = db.query(User).filter(User.username == BOROOUPLOADER_USERNAME).first()
    if user is None:
        user = User(
            username=BOROOUPLOADER_USERNAME,
            email=None,
            password_hash=hash_password(BOROOUPLOADER_PASSWORD),
            role=UserRole.UPLOADER,
            is_active=True,
            is_banned=False,
            can_upload=True,
            invite_quota=0,
            can_view_questionable=True,
            can_view_explicit=True,
            tag_blacklist="",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    changed = False
    if not user.is_active:
        user.is_active = True
        changed = True
    if user.is_banned:
        user.is_banned = False
        changed = True
    if not user.can_upload:
        user.can_upload = True
        changed = True
    if user.role != UserRole.UPLOADER:
        user.role = UserRole.UPLOADER
        changed = True
    if user.invite_quota != 0:
        user.invite_quota = 0
        changed = True
    if not user.can_view_questionable:
        user.can_view_questionable = True
        changed = True
    if not user.can_view_explicit:
        user.can_view_explicit = True
        changed = True
    if changed:
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def enqueue_board_import(run_id: int) -> None:
    redis = get_redis_client()
    redis.rpush(BOARD_IMPORT_QUEUE, str(run_id))


def claim_next_run(redis, stop_event: threading.Event) -> int | None:
    while not stop_event.is_set():
        item = redis.blpop(BOARD_IMPORT_QUEUE, timeout=2)
        if not item:
            continue
        _queue_name, payload = item
        try:
            return int(payload)
        except (TypeError, ValueError):
            continue
    return None


def normalize_manual_tags(raw_tags: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for tag in raw_tags:
        normalized = tag.strip().lower().replace(" ", "_")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def get_or_create_tag(db: Session, tag_name: str) -> Tag:
    tag = db.query(Tag).filter(Tag.name_normalized == tag_name).first()
    if tag:
        return tag
    tag = Tag(name_normalized=tag_name, display_name=tag_name, category=TagCategory.GENERAL)
    db.add(tag)
    db.flush()
    return tag


def add_manual_tags_to_image(db: Session, image_id: str, tag_names: list[str]) -> None:
    normalized = normalize_manual_tags(tag_names)
    if not normalized:
        return
    image = (
        db.query(Image)
        .options(selectinload(Image.tags).selectinload(ImageTag.tag))
        .filter(Image.id == image_id)
        .first()
    )
    if image is None:
        return

    existing_names = {image_tag.tag.name_normalized for image_tag in image.tags}
    for tag_name in normalized:
        if tag_name in existing_names:
            continue
        tag = get_or_create_tag(db, tag_name)
        db.add(
            ImageTag(
                image_id=image.id,
                tag_id=tag.id,
                source=TagSource.USER,
                confidence=None,
                is_manual=True,
            )
        )
        existing_names.add(tag_name)

    db.flush()
    rule_map = load_rating_rule_map(db)
    if rule_map:
        refreshed_image = (
            db.query(Image)
            .options(selectinload(Image.tags).selectinload(ImageTag.tag))
            .filter(Image.id == image.id)
            .first()
        )
        if refreshed_image is not None:
            reclassify_image_from_rules(db, refreshed_image, rule_map)


def run_hour_bucket_key() -> str:
    return f"nextboo:board-import:budget:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"


def remaining_hourly_budget(redis, hourly_limit: int) -> int:
    current = redis.get(run_hour_bucket_key())
    used = int(current or "0")
    return max(hourly_limit - used, 0)


def consume_hourly_budget(redis, count: int) -> None:
    if count <= 0:
        return
    key = run_hour_bucket_key()
    redis.incrby(key, count)
    redis.expire(key, 7200)


def append_event(
    db: Session,
    run: BoardImportRun,
    *,
    level: str,
    event_type: str,
    message: str,
    remote_post_id: str | None = None,
    job_id: int | None = None,
    image_id: str | None = None,
) -> None:
    event = BoardImportEvent(
        run_id=run.id,
        level=level,
        event_type=event_type,
        message=message,
        remote_post_id=remote_post_id,
        job_id=job_id,
        image_id=image_id,
        is_error=level in {"error", "warning"},
    )
    run.current_message = message
    run.last_event_at = datetime.now(timezone.utc)
    db.add(event)
    db.add(run)
    db.commit()


def update_run_counts(db: Session, run: BoardImportRun, **values: int | str | None) -> None:
    for key, value in values.items():
        setattr(run, key, value)
    run.updated_at = datetime.now(timezone.utc)
    db.add(run)
    db.commit()


def is_run_cancelled(db: Session, run_id: int) -> bool:
    run = db.get(BoardImportRun, run_id)
    if run is None:
        return True
    return run.status == "cancelled"


def wait_for_upload_pipeline_batch(
    db: Session,
    run: BoardImportRun,
    pipeline_batch_id: int | None,
    accepted_items: list[tuple[int, str, list[str]]],
) -> None:
    if not accepted_items or pipeline_batch_id is None:
        return

    deadline = time.time() + BOARD_IMPORT_JOB_TIMEOUT_SECONDS
    accepted_item_map = {item_id: (remote_post_id, tag_list) for item_id, remote_post_id, tag_list in accepted_items}
    seen_item_ids: set[int] = set()
    announced_job_ids: set[int] = set()
    completed_posts = run.completed_posts
    duplicate_posts = run.duplicate_posts
    failed_posts = run.failed_posts
    queued_posts = run.queued_posts

    while time.time() < deadline:
        if is_run_cancelled(db, run.id):
            return

        batch = db.get(UploadPipelineBatch, pipeline_batch_id)
        if batch is not None and batch.linked_import_id is not None and run.source_import_batch_id != batch.linked_import_id:
            update_run_counts(db, run, source_import_batch_id=batch.linked_import_id)
            run = db.get(BoardImportRun, run.id) or run

        items = (
            db.query(UploadPipelineItem)
            .filter(UploadPipelineItem.id.in_(accepted_item_map.keys()))
            .all()
        )
        for item in items:
            remote_post_id, tag_list = accepted_item_map[item.id]
            if item.linked_job_id is not None and item.linked_job_id not in announced_job_ids:
                announced_job_ids.add(item.linked_job_id)
                if queued_posts < len(accepted_item_map):
                    queued_posts += 1
                append_event(
                    db,
                    run,
                    level="info",
                    event_type="queued",
                    message=f"Queued remote post {remote_post_id} as worker job {item.linked_job_id}.",
                    remote_post_id=remote_post_id,
                    job_id=item.linked_job_id,
                )
            if item.id in seen_item_ids:
                continue

            if item.status == "completed" and item.linked_image_id:
                add_manual_tags_to_image(db, item.linked_image_id, tag_list)
                completed_posts += 1
                append_event(
                    db,
                    run,
                    level="info",
                    event_type="completed",
                    message=f"Imported remote post {remote_post_id} into image {item.linked_image_id}.",
                    remote_post_id=remote_post_id,
                    job_id=item.linked_job_id,
                    image_id=item.linked_image_id,
                )
            elif item.status == "duplicate":
                duplicate_posts += 1
                append_event(
                    db,
                    run,
                    level="warning",
                    event_type="duplicate",
                    message=item.detail_message or f"Remote post {remote_post_id} matched an existing image.",
                    remote_post_id=remote_post_id,
                    job_id=item.linked_job_id,
                    image_id=item.linked_image_id,
                )
            elif item.status in {"failed", "rejected"}:
                failed_posts += 1
                append_event(
                    db,
                    run,
                    level="error",
                    event_type="job_failed",
                    message=item.detail_message or f"Worker failed remote post {remote_post_id}.",
                    remote_post_id=remote_post_id,
                    job_id=item.linked_job_id,
                )
            else:
                continue
            seen_item_ids.add(item.id)

        update_run_counts(
            db,
            run,
            queued_posts=queued_posts,
            completed_posts=completed_posts,
            duplicate_posts=duplicate_posts,
            failed_posts=failed_posts,
        )
        if len(seen_item_ids) >= len(accepted_items):
            return

        time.sleep(BOARD_IMPORT_POLL_SECONDS)

    remaining = len(accepted_items) - len(seen_item_ids)
    append_event(
        db,
        run,
        level="error",
        event_type="timeout",
        message=f"Timed out waiting for {remaining} board-import pipeline items.",
    )
    update_run_counts(db, run, failed_posts=failed_posts + max(remaining, 1))


def redis_entries(
    *,
    job_ids: set[int] | None = None,
    import_batch_id: int | None = None,
) -> list[dict[str, object]]:
    redis = get_redis_client()
    entries = redis.lrange(OUTCOME_STREAM_KEY, 0, OUTCOME_SCAN_LIMIT - 1)
    results: list[dict[str, object]] = []
    for raw in entries:
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        payload_job_id = payload.get("job_id")
        payload_import_batch_id = payload.get("import_batch_id")
        if job_ids is not None:
            try:
                normalized_job_id = int(payload_job_id)
            except (TypeError, ValueError):
                normalized_job_id = None
            if normalized_job_id not in job_ids:
                continue
        if import_batch_id is not None and int(payload_import_batch_id or 0) != import_batch_id:
            continue
        results.append(payload)
    return list(reversed(results))


def finalize_run(db: Session, run: BoardImportRun) -> None:
    run.finished_at = datetime.now(timezone.utc)
    if run.completed_posts > 0 or run.duplicate_posts > 0:
        run.status = "done"
        run.current_message = (
            f"Finished board import with {run.completed_posts} completed images, "
            f"{run.duplicate_posts} duplicates and {run.failed_posts} failures."
        )
    else:
        run.status = "failed"
        run.error_summary = run.error_summary or "Board import completed without any accepted images."
        run.current_message = run.error_summary
    db.add(run)
    db.commit()
    append_event(
        db,
        run,
        level="info" if run.status == "done" else "error",
        event_type="finished",
        message=run.current_message or "Board import finished.",
    )


def reconcile_run_from_outcomes(db: Session, run: BoardImportRun) -> bool:
    queued_events = (
        db.query(BoardImportEvent)
        .filter(BoardImportEvent.run_id == run.id, BoardImportEvent.event_type == "queued")
        .order_by(BoardImportEvent.id.asc())
        .all()
    )
    queued_job_ids = {event.job_id for event in queued_events if event.job_id is not None}
    if not queued_job_ids:
        return False

    outcome_rows = redis_entries(job_ids=queued_job_ids, import_batch_id=run.source_import_batch_id)
    if not outcome_rows:
        return False

    seen_job_ids: set[int] = set()
    accepted_count = 0
    duplicate_count = 0
    failed_count = 0
    for payload in outcome_rows:
        job_id = payload.get("job_id")
        if not isinstance(job_id, int) or job_id not in queued_job_ids or job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)
        outcome = str(payload.get("outcome") or "")
        if outcome == "accepted":
            accepted_count += 1
        elif outcome == "duplicate":
            duplicate_count += 1
        else:
            failed_count += 1

    if not seen_job_ids:
        return False

    run.completed_posts = max(run.completed_posts, accepted_count)
    run.duplicate_posts = max(run.duplicate_posts, duplicate_count)
    run.failed_posts = max(run.failed_posts, failed_count)
    if len(seen_job_ids) >= len(queued_job_ids):
        finalize_run(db, run)
        return True

    update_run_counts(
        db,
        run,
        completed_posts=run.completed_posts,
        duplicate_posts=run.duplicate_posts,
        failed_posts=run.failed_posts,
    )
    return False


def process_run(run_id: int) -> None:
    redis = get_redis_client()
    with SessionLocal() as db:
        run = db.get(BoardImportRun, run_id)
        if run is None:
            return
        if run.status not in {"pending", "retrying"}:
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.current_message = "Preparing board import."
        db.add(run)
        db.commit()

        uploader = ensure_boroo_uploader_user(db)
        append_event(
            db,
            run,
            level="info",
            event_type="start",
            message=f"Starting board import from {run.board_name} for tags '{run.tag_query}'.",
        )

        try:
            preset = get_preset(run.board_name)
            adapter = build_adapter(preset)
            tags = parse_csv_tags(run.tag_query)
            if not tags:
                raise RuntimeError("Tag query is empty after normalization.")

            remaining_budget = remaining_hourly_budget(redis, run.hourly_limit)
            if remaining_budget <= 0:
                raise RuntimeError(f"Hourly board import budget of {run.hourly_limit} images is exhausted.")

            fetch_limit = min(run.requested_limit, remaining_budget)
            append_event(
                db,
                run,
                level="info",
                event_type="search",
                message=f"Searching {preset.name} for up to {fetch_limit} posts.",
            )
            posts = adapter.search_posts(tags, fetch_limit)
            update_run_counts(db, run, discovered_posts=len(posts))
            if not posts:
                run.status = "done"
                run.finished_at = datetime.now(timezone.utc)
                run.current_message = "No remote posts found."
                db.add(run)
                db.commit()
                append_event(db, run, level="warning", event_type="empty", message="No remote posts matched the query.")
                return

            with tempfile.TemporaryDirectory(prefix="nextboo_board_import_") as temp_dir:
                temp_root = Path(temp_dir)
                staged_uploads: list[dict[str, str | int]] = []
                remote_post_map: dict[str, tuple[str, list[str]]] = {}
                failed_posts = run.failed_posts
                downloaded_posts = run.downloaded_posts

                for post in posts:
                    if is_run_cancelled(db, run.id):
                        return
                    try:
                        local_path = download_remote_post(adapter.session, post, temp_root)
                        quarantine_path, checksum_sha256 = StorageService().stage_local_file_to_quarantine(local_path)
                        file_size = Path(quarantine_path).stat().st_size
                        client_key = f"{post.board}:{post.post_id}"
                        staged_uploads.append(
                            {
                                "client_key": client_key,
                                "filename": post.filename,
                                "quarantine_path": quarantine_path,
                                "checksum_sha256": checksum_sha256,
                                "file_size": file_size,
                                "mime_type": getattr(post, "mime_type", None) or mimetypes.guess_type(post.filename)[0] or "application/octet-stream",
                            }
                        )
                        remote_post_map[client_key] = (post.post_id, post.tags)
                        downloaded_posts += 1
                        append_event(
                            db,
                            run,
                            level="info",
                            event_type="downloaded",
                            message=f"Downloaded remote post {post.post_id}.",
                            remote_post_id=post.post_id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        failed_posts += 1
                        append_event(
                            db,
                            run,
                            level="error",
                            event_type="download_failed",
                            message=f"Failed to download remote post {post.post_id}: {exc}",
                            remote_post_id=post.post_id,
                        )
                update_run_counts(db, run, downloaded_posts=downloaded_posts, failed_posts=failed_posts)

                if not staged_uploads:
                    run.status = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    run.error_summary = "No remote posts could be downloaded."
                    db.add(run)
                    db.commit()
                    return

                upload_response = finalize_staged_uploads(
                    db,
                    redis,
                    uploader,
                    staged_uploads,
                    source_type=ImportSourceType.API,
                    source_name=f"board-import:{run.board_name}:{run.id}",
                    rejected=[],
                )
                pipeline_batch_id = upload_response.meta.get("pipeline_batch_id")
                queued_posts = run.queued_posts
                duplicate_posts = run.duplicate_posts
                failed_posts = run.failed_posts
                accepted_items: list[tuple[int, str, list[str]]] = []

                for accepted in upload_response.data:
                    remote_post_id, tag_list = remote_post_map.get(accepted.client_key, (accepted.client_key, tags))
                    accepted_items.append((accepted.upload_item_id, remote_post_id, tag_list))

                for rejected in upload_response.rejected:
                    remote_post_id, _tag_list = remote_post_map.get(rejected.client_key, (rejected.client_key, tags))
                    if "duplicate" in rejected.error.lower():
                        duplicate_posts += 1
                        level = "warning"
                        event_type = "duplicate"
                    else:
                        failed_posts += 1
                        level = "error"
                        event_type = "upload_failed"
                    append_event(
                        db,
                        run,
                        level=level,
                        event_type=event_type,
                        message=f"Rejected remote post {remote_post_id}: {rejected.error}",
                        remote_post_id=remote_post_id,
                    )

                consume_hourly_budget(redis, downloaded_posts)
                update_run_counts(
                    db,
                    run,
                    queued_posts=queued_posts,
                    duplicate_posts=duplicate_posts,
                    failed_posts=failed_posts,
                )

                wait_for_upload_pipeline_batch(
                    db,
                    run,
                    int(pipeline_batch_id) if str(pipeline_batch_id).isdigit() else None,
                    accepted_items,
                )

            run = db.get(BoardImportRun, run_id)
            if run is None:
                return
            if run.status == "cancelled":
                return
            finalize_run(db, run)
        except Exception as exc:  # noqa: BLE001
            logger.exception("board import run failed run_id=%s", run_id)
            run = db.get(BoardImportRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.error_summary = str(exc)
            run.current_message = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            db.add(run)
            db.commit()
            append_event(
                db,
                run,
                level="error",
                event_type="failed",
                message=f"Board import failed: {exc}",
            )


def recover_stale_runs() -> None:
    with SessionLocal() as db:
        stale_runs = (
            db.query(BoardImportRun)
            .filter(BoardImportRun.status.in_(["pending", "running"]))
            .all()
        )
        now = datetime.now(timezone.utc)
        for run in stale_runs:
            if reconcile_run_from_outcomes(db, run):
                continue
            if not run.started_at:
                run.status = "pending"
                db.add(run)
                continue
            age_seconds = (now - run.started_at).total_seconds()
            if age_seconds > BOARD_IMPORT_JOB_TIMEOUT_SECONDS:
                run.status = "failed"
                run.finished_at = now
                run.error_summary = "Board import runner timed out or restarted during processing."
                run.current_message = run.error_summary
                db.add(run)
                db.commit()
                append_event(
                    db,
                    run,
                    level="error",
                    event_type="stale",
                    message=run.error_summary,
                )
            else:
                run.status = "pending"
                db.add(run)
                db.commit()
                enqueue_board_import(run.id)


def board_import_worker_loop(stop_event: threading.Event) -> None:
    redis = get_redis_client()
    recover_stale_runs()
    logger.info("board import runner started queue=%s", BOARD_IMPORT_QUEUE)
    while not stop_event.is_set():
        run_id = claim_next_run(redis, stop_event)
        if run_id is None:
            continue
        process_run(run_id)
    logger.info("board import runner stopped")
