import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.db import get_connection
from app.pipeline import AnalysisFrameGenerationError, ProcessedImage, SourceFileMissingError, process_image
from app.retag_existing import backfill_preview_variants, retag_existing
from app.settings import get_settings
from app.storage import StorageService
from app.tagger import build_tagger
from redis import Redis


logger = logging.getLogger("worker.queue")


NON_RETRYABLE_EXCEPTIONS = (SourceFileMissingError,)
TERMINAL_FAILURE_EXCEPTIONS = (AnalysisFrameGenerationError,)
OUTCOME_STREAM_KEY = "nextboo:jobs:outcomes"
OUTCOME_STREAM_LIMIT = 500

RATING_ORDER = {
    "general": 0,
    "sensitive": 1,
    "questionable": 2,
    "explicit": 3,
}

DEFAULT_RATING_RULE_BOOSTS = {
    "general": 0.18,
    "sensitive": 0.20,
    "questionable": 0.24,
    "explicit": 0.34,
}

AUTO_TAG_SOURCE_ENUM = "AUTO"
SYSTEM_TAG_SOURCE_ENUM = "SYSTEM"
VISIBLE_STATUS_ENUM = "VISIBLE"
HIDDEN_STATUS_ENUM = "HIDDEN"
NEAR_DUPLICATE_STATUS_OPEN = "open"

MaintenanceAction = Literal["retag_all", "preview_backfill"]


def normalize_rule_rating(value: object) -> str:
    normalized = str(value).strip().lower()
    if normalized.startswith("rating."):
        normalized = normalized.split(".", 1)[1]
    return normalized


class WorkerService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = Redis.from_url(self.settings.redis_dsn, decode_responses=True)
        self.storage = StorageService()
        try:
            self.tagger = build_tagger(self.settings.tagger_provider)
        except TypeError:
            self.tagger = build_tagger()
        self.worker_id = f"worker-{Path('/etc/hostname').read_text().strip() if Path('/etc/hostname').exists() else 'local'}"

    def touch_worker_presence(self) -> None:
        self.redis.set(
            f"nextboo:workers:active:{self.worker_id}",
            datetime.now(timezone.utc).isoformat(),
            ex=self.settings.worker_presence_ttl_seconds,
        )

    def poll_job(self, timeout_seconds: int = 5) -> tuple[str, int | dict[str, object]] | None:
        item = self.redis.blpop([self.settings.maintenance_queue_name, self.settings.ingest_queue_name], timeout=timeout_seconds)
        if not item:
            return None
        queue_name, raw_payload = item
        if queue_name == self.settings.maintenance_queue_name:
            return ("maintenance", json.loads(raw_payload))
        return ("ingest", int(raw_payload))

    def run_forever(self) -> None:
        self.storage.ensure_dirs()
        self.touch_worker_presence()
        self.recover_stale_jobs(reason="startup")
        while True:
            self.touch_worker_presence()
            item = self.poll_job()
            if item is None:
                self.recover_stale_jobs(reason="idle")
                continue
            item_type, payload = item
            try:
                if item_type == "maintenance":
                    self.handle_maintenance(payload)
                    continue
                self.handle_job(payload)
            except Exception:
                if item_type == "maintenance":
                    logger.exception("maintenance action failed payload=%s", payload)
                else:
                    logger.exception("job failed unexpectedly job_id=%s", payload)

    def recover_stale_jobs(self, reason: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, queue_path, retry_count, max_retries, import_batch_id, locked_by, locked_at
                    FROM jobs
                    WHERE status = 'RUNNING'::job_status
                      AND locked_at IS NOT NULL
                      AND locked_at < NOW() - (%s * INTERVAL '1 second')
                    ORDER BY locked_at ASC
                    """,
                    (self.settings.stale_job_timeout_seconds,),
                )
                stale_jobs = cur.fetchall()
                if not stale_jobs:
                    conn.commit()
                    return

                for job in stale_jobs:
                    self.storage.remove_job_workdir(job["id"])
                    if job["retry_count"] < 1:
                        cur.execute(
                            """
                            UPDATE jobs
                            SET status = 'RETRYING'::job_status,
                                retry_count = retry_count + 1,
                                last_error = %s,
                                locked_by = NULL,
                                locked_at = NULL,
                                updated_at = NOW()
                            WHERE id = %s
                            """,
                            (f"stale job timeout recovered during {reason}", job["id"]),
                        )
                        self.redis.rpush(self.settings.ingest_queue_name, str(job["id"]))
                        logger.warning(
                            "requeued stale running job job_id=%s locked_by=%s locked_at=%s reason=%s",
                            job["id"],
                            job["locked_by"],
                            job["locked_at"],
                            reason,
                        )
                        continue

                    self._drop_job_with_audit(job, f"stale job timeout exceeded after one retry during {reason}", "stale_timeout", cur=cur)
                    logger.warning(
                        "dropped stale running job job_id=%s locked_by=%s locked_at=%s reason=%s",
                        job["id"],
                        job["locked_by"],
                        job["locked_at"],
                        reason,
                    )
                conn.commit()

    def handle_maintenance(self, payload: dict[str, object]) -> None:
        action = str(payload.get("action", "")).strip().lower()
        if action not in {"retag_all", "preview_backfill"}:
            logger.warning("ignored unknown maintenance action action=%s payload=%s", action, payload)
            return

        self.redis.delete(self.settings.maintenance_pending_key_for_action(action))
        self.redis.set(self.settings.maintenance_running_key_for_action(action), self.worker_id, ex=86400)
        requested_by_username = str(payload.get("requested_by_username", "unknown"))
        logger.warning(
            "starting maintenance action=%s provider=%s requested_by=%s",
            action,
            self.settings.tagger_provider,
            requested_by_username,
        )
        try:
            if action == "retag_all":
                processed, failed = retag_existing()
            else:
                processed, failed = backfill_preview_variants()
            logger.warning(
                "completed maintenance action=%s provider=%s processed=%s failed=%s",
                action,
                self.settings.tagger_provider,
                processed,
                failed,
            )
        finally:
            self.redis.delete(self.settings.maintenance_running_key_for_action(action))

    def handle_job(self, job_id: int) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'RUNNING'::job_status, locked_by = %s, locked_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status IN ('QUEUED'::job_status, 'RETRYING'::job_status)
                    RETURNING id, queue_path, retry_count, max_retries, import_batch_id
                    """,
                    (self.worker_id, job_id),
                )
                job = cur.fetchone()
                conn.commit()

        if not job:
            logger.info("job already claimed or unavailable job_id=%s", job_id)
            return

        queue_path = job["queue_path"]
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_job,
            args=(job["id"], heartbeat_stop),
            daemon=True,
            name=f"job-heartbeat-{job['id']}",
        )
        heartbeat_thread.start()
        try:
            processed = process_image(job_id, queue_path, self.settings.thumb_max_edge, self.storage, self.tagger)
            self._register_success(job, processed)
            source = Path(queue_path)
            if source.exists():
                source.unlink()
        except TERMINAL_FAILURE_EXCEPTIONS as exc:
            self._register_terminal_failure(job, str(exc))
            source = Path(queue_path)
            if source.exists():
                self.storage.move_to_failed(source)
            logger.warning("marked terminal processing failure job_id=%s error=%s", job["id"], exc)
            return
        except Exception as exc:
            if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
                self._drop_job_with_audit(job, str(exc), event_type="file_missing")
                source = Path(queue_path)
                if source.exists():
                    source.unlink()
                logger.warning("dropped non-retryable job job_id=%s error=%s", job["id"], exc)
                return
            terminal_failure = self._register_failure(job, str(exc))
            source = Path(queue_path)
            if terminal_failure and source.exists():
                self.storage.move_to_failed(source)
            raise
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
            self.storage.remove_job_workdir(job_id)

    def _heartbeat_job(self, job_id: int, stop_event: threading.Event) -> None:
        while not stop_event.wait(self.settings.job_heartbeat_seconds):
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE jobs
                            SET locked_at = NOW(), updated_at = NOW()
                            WHERE id = %s AND status = 'RUNNING'::job_status
                            """,
                            (job_id,),
                        )
                        conn.commit()
                self.touch_worker_presence()
            except Exception:
                logger.exception("failed to heartbeat running job job_id=%s", job_id)

    def _register_success(self, job: dict, processed: ProcessedImage) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                self._apply_rating_rules(cur, processed)
                cur.execute("SELECT id FROM images WHERE checksum_sha256 = %s", (processed.source_hash,))
                duplicate = cur.fetchone()
                if duplicate:
                    processed.original_path.unlink(missing_ok=True)
                    processed.thumb_path.unlink(missing_ok=True)
                    if processed.preview_path:
                        processed.preview_path.unlink(missing_ok=True)
                    self._record_outcome(
                        outcome="duplicate",
                        job_id=job["id"],
                        import_batch_id=job["import_batch_id"],
                        message=f"Matched existing image {duplicate['id']}",
                        image_id=str(duplicate["id"]),
                    )
                    if job["import_batch_id"] is not None:
                        cur.execute(
                            """
                            UPDATE imports
                            SET processed_files = processed_files + 1, updated_at = NOW()
                            WHERE id = %s
                            """,
                            (job["import_batch_id"],),
                        )
                    self._prune_completed_job(cur, job["id"], job["import_batch_id"])
                    conn.commit()
                    self.redis.publish("jobs:events", json.dumps({"job_id": job["id"], "status": "done"}))
                    return

                submitted_by_user_id = None
                if job["import_batch_id"] is not None:
                    cur.execute(
                        "SELECT submitted_by_user_id FROM imports WHERE id = %s",
                        (job["import_batch_id"],),
                    )
                    import_row = cur.fetchone()
                    if import_row:
                        submitted_by_user_id = import_row["submitted_by_user_id"]

                cur.execute(
                    """
                    INSERT INTO images (
                        id, uuid_short, original_filename, mime_type_original, file_size_original,
                        file_size_stored, checksum_sha256, perceptual_hash, width, height,
                        duration_seconds, frame_rate, has_audio, video_codec, audio_codec,
                        aspect_ratio, storage_ext, rating, nsfw_score, source_type, source_path,
                        uploaded_by_user_id, import_batch_id,
                        processing_status, processing_error, auto_model_version, nsfw_model_version,
                        created_at, imported_at, processed_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::rating, %s, 'web', %s,
                        %s, %s,
                        'READY'::processing_status, NULL, %s, %s,
                        NOW(), NOW(), %s, NOW()
                    )
                    """,
                    (
                        processed.image_id,
                        processed.uuid_short,
                        Path(job["queue_path"]).name,
                        processed.original_mime_type,
                        Path(job["queue_path"]).stat().st_size if Path(job["queue_path"]).exists() else processed.original_size,
                        processed.original_size,
                        processed.source_hash,
                        processed.perceptual_hash,
                        processed.width,
                        processed.height,
                        processed.duration_seconds,
                        processed.frame_rate,
                        processed.has_audio,
                        processed.video_codec,
                        processed.audio_codec,
                        processed.aspect_ratio,
                        processed.storage_ext,
                        processed.tag_prediction.rating.upper(),
                        processed.tag_prediction.rating_score,
                        job["queue_path"],
                        submitted_by_user_id,
                        job["import_batch_id"],
                        processed.tag_prediction.model_version,
                        processed.tag_prediction.model_version,
                        processed.processed_at,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO image_variants (image_id, variant_type, relative_path, mime_type, file_size, width, height, created_at)
                    VALUES (%s, 'ORIGINAL'::variant_type, %s, %s, %s, %s, %s, NOW()),
                           (%s, 'THUMB'::variant_type, %s, 'image/webp', %s, %s, %s, NOW())
                    """,
                    (
                        processed.image_id,
                        str(processed.original_path.relative_to(self.storage.content_path.parent)),
                        processed.original_mime_type,
                        processed.original_size,
                        processed.width,
                        processed.height,
                        processed.image_id,
                        str(processed.thumb_path.relative_to(self.storage.thumb_path.parent)),
                        processed.thumb_size,
                        min(processed.width, self.settings.thumb_max_edge),
                        min(processed.height, self.settings.thumb_max_edge),
                    ),
                )
                if processed.preview_path and processed.preview_size and processed.preview_mime_type:
                    cur.execute(
                        """
                        INSERT INTO image_variants (image_id, variant_type, relative_path, mime_type, file_size, width, height, created_at)
                        VALUES (%s, 'PREVIEW'::variant_type, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            processed.image_id,
                            str(processed.preview_path.relative_to(self.storage.thumb_path.parent)),
                            processed.preview_mime_type,
                            processed.preview_size,
                            processed.preview_width or min(processed.width, self.settings.thumb_max_edge),
                            processed.preview_height or min(processed.height, self.settings.thumb_max_edge),
                        ),
                    )
                self._upsert_tags(cur, processed)
                self._apply_danger_tags(cur, processed)
                self._register_near_duplicates(cur, processed)
                if job["import_batch_id"] is not None:
                    cur.execute(
                        """
                        UPDATE imports
                        SET processed_files = processed_files + 1,
                            status = CASE WHEN processed_files + 1 >= total_files THEN 'DONE'::import_status ELSE status END,
                            finished_at = CASE WHEN processed_files + 1 >= total_files THEN NOW() ELSE finished_at END,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (job["import_batch_id"],),
                    )
                self._prune_completed_job(cur, job["id"], job["import_batch_id"])
                conn.commit()
                self._record_outcome(
                    outcome="accepted",
                    job_id=job["id"],
                    import_batch_id=job["import_batch_id"],
                    message="Image accepted and displayed.",
                    image_id=processed.image_id,
                )
                self.redis.publish("jobs:events", json.dumps({"job_id": job["id"], "status": "done"}))

    def _apply_rating_rules(self, cur, processed: ProcessedImage) -> None:
        present_tags = (
            set(processed.tag_prediction.general_tags)
            | set(processed.tag_prediction.character_tags)
            | set(processed.tag_prediction.copyright_tags)
            | set(processed.tag_prediction.artist_tags)
            | set(processed.tag_prediction.meta_tags)
        )
        if not present_tags:
            return
        cur.execute(
            """
            SELECT t.name_normalized, r.target_rating, r.boost
            FROM tag_rating_rules r
            JOIN tags t ON t.id = r.tag_id
            WHERE r.is_enabled = TRUE
            """
        )
        rows = cur.fetchall()
        if not rows:
            return

        strongest_rule = processed.tag_prediction.rating
        rating_scores = {
            "general": float(processed.tag_prediction.rating_scores.get("general", 0.0)),
            "sensitive": float(processed.tag_prediction.rating_scores.get("sensitive", 0.0)),
            "questionable": float(processed.tag_prediction.rating_scores.get("questionable", 0.0)),
            "explicit": float(processed.tag_prediction.rating_scores.get("explicit", 0.0)),
        }

        for row in rows:
            tag_name = row["name_normalized"]
            if tag_name not in present_tags:
                continue
            target_rating = normalize_rule_rating(row["target_rating"])
            boost = float(row["boost"] or DEFAULT_RATING_RULE_BOOSTS.get(target_rating, 0.2))
            if target_rating == "general":
                rating_scores["general"] = min(1.0, rating_scores["general"] + boost)
            elif target_rating == "sensitive":
                rating_scores["sensitive"] = min(1.0, rating_scores["sensitive"] + boost)
            elif target_rating == "questionable":
                rating_scores["questionable"] = min(1.0, rating_scores["questionable"] + boost)
                rating_scores["sensitive"] = min(1.0, rating_scores["sensitive"] + (boost / 2))
            elif target_rating == "explicit":
                rating_scores["explicit"] = min(1.0, rating_scores["explicit"] + boost)
            if RATING_ORDER.get(target_rating, 0) > RATING_ORDER.get(strongest_rule, 0):
                strongest_rule = target_rating

        from app.tagger import decide_rating

        next_rating, next_score = decide_rating(rating_scores, processed.tag_prediction.general_tags)
        if RATING_ORDER.get(strongest_rule, 0) > RATING_ORDER.get(next_rating, 0):
            next_rating = strongest_rule
            next_score = max(next_score, rating_scores.get("questionable", 0.0), rating_scores.get("explicit", 0.0))

        processed.tag_prediction.rating = next_rating
        processed.tag_prediction.rating_score = next_score
        processed.tag_prediction.rating_scores = rating_scores

    def _upsert_tags(self, cur, processed: ProcessedImage) -> None:
        all_tags = [
            ("general", name, score) for name, score in processed.tag_prediction.general_tags.items()
        ] + [
            ("character", name, score) for name, score in processed.tag_prediction.character_tags.items()
        ] + [
            ("copyright", name, score) for name, score in processed.tag_prediction.copyright_tags.items()
        ] + [
            ("artist", name, score) for name, score in processed.tag_prediction.artist_tags.items()
        ] + [
            ("meta", name, score) for name, score in processed.tag_prediction.meta_tags.items()
        ]
        for category, name, score in all_tags:
            display_name = name
            cur.execute(
                """
                INSERT INTO tags (name_normalized, display_name, category, is_active, is_locked, created_at, updated_at)
                VALUES (%s, %s, %s::tag_category, TRUE, FALSE, NOW(), NOW())
                ON CONFLICT (name_normalized)
                DO UPDATE SET display_name = EXCLUDED.display_name, category = EXCLUDED.category, updated_at = NOW()
                RETURNING id
                """,
                (name, display_name, category.upper()),
            )
            row = cur.fetchone()
            tag_id = row["id"]
            cur.execute(
                f"""
                INSERT INTO image_tags (image_id, tag_id, source, confidence, is_manual, created_at, updated_at)
                VALUES (%s, %s, '{AUTO_TAG_SOURCE_ENUM}'::tag_source, %s, FALSE, NOW(), NOW())
                ON CONFLICT (image_id, tag_id, source)
                DO UPDATE SET confidence = EXCLUDED.confidence, updated_at = NOW()
                """,
                (processed.image_id, tag_id, score),
            )

        system_tags = [processed.media_kind]
        for name in system_tags:
            cur.execute(
                """
                INSERT INTO tags (name_normalized, display_name, category, is_active, is_locked, created_at, updated_at)
                VALUES (%s, %s, 'META'::tag_category, TRUE, FALSE, NOW(), NOW())
                ON CONFLICT (name_normalized)
                DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                (name, name),
            )
            row = cur.fetchone()
            cur.execute(
                f"""
                INSERT INTO image_tags (image_id, tag_id, source, confidence, is_manual, created_at, updated_at)
                VALUES (%s, %s, '{SYSTEM_TAG_SOURCE_ENUM}'::tag_source, NULL, FALSE, NOW(), NOW())
                ON CONFLICT (image_id, tag_id, source)
                DO UPDATE SET updated_at = NOW()
                """,
                (processed.image_id, row["id"]),
            )

    def _apply_danger_tags(self, cur, processed: ProcessedImage) -> None:
        present_tags = (
            set(processed.tag_prediction.general_tags)
            | set(processed.tag_prediction.character_tags)
            | set(processed.tag_prediction.copyright_tags)
            | set(processed.tag_prediction.artist_tags)
            | set(processed.tag_prediction.meta_tags)
        )
        if not present_tags:
            return
        cur.execute(
            """
            SELECT d.id, d.reason, t.id AS tag_id, t.name_normalized
            FROM danger_tags d
            JOIN tags t ON t.id = d.tag_id
            WHERE d.is_enabled = TRUE
            """
        )
        rows = cur.fetchall()
        hits = [row for row in rows if row["name_normalized"] in present_tags]
        if not hits:
            return
        cur.execute(
            f"""
            INSERT INTO image_moderation (image_id, visibility_status, reason, note, acted_by_user_id, acted_at)
            VALUES (%s, '{HIDDEN_STATUS_ENUM}'::visibility_status, %s, %s, NULL, NOW())
            ON CONFLICT (image_id)
            DO UPDATE SET visibility_status = '{HIDDEN_STATUS_ENUM}'::visibility_status,
                          reason = EXCLUDED.reason,
                          note = EXCLUDED.note,
                          acted_at = NOW()
            """,
            (
                processed.image_id,
                "danger_tag_auto_hold",
                ", ".join(sorted({row["name_normalized"] for row in hits})),
            ),
        )
        for row in hits:
            cur.execute(
                """
                INSERT INTO image_danger_hits (image_id, tag_id, created_at, reason)
                VALUES (%s, %s, NOW(), %s)
                """,
                (processed.image_id, row["tag_id"], row["reason"]),
            )

    def _register_failure(self, job: dict, error_message: str) -> bool:
        with get_connection() as conn:
            with conn.cursor() as cur:
                next_retry = job["retry_count"] + 1
                if next_retry <= job["max_retries"]:
                    cur.execute(
                        """
                        UPDATE jobs
                        SET status = 'RETRYING'::job_status, retry_count = %s, last_error = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (next_retry, error_message, job["id"]),
                    )
                    conn.commit()
                    self.redis.rpush(self.settings.ingest_queue_name, str(job["id"]))
                    return False

                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED'::job_status, retry_count = %s, last_error = %s, finished_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (next_retry, error_message, job["id"]),
                )
                if job["import_batch_id"] is not None:
                    cur.execute(
                        """
                        UPDATE imports
                        SET failed_files = failed_files + 1,
                            status = 'FAILED'::import_status,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (job["import_batch_id"],),
                    )
                conn.commit()
                self._record_outcome(
                    outcome="failed",
                    job_id=job["id"],
                    import_batch_id=job["import_batch_id"],
                    message=error_message,
                    image_id=None,
                )
                self.redis.publish("jobs:events", json.dumps({"job_id": job["id"], "status": "failed"}))
                return True

    def _register_terminal_failure(self, job: dict, error_message: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                next_retry = job["retry_count"] + 1
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED'::job_status, retry_count = %s, last_error = %s, finished_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (next_retry, error_message, job["id"]),
                )
                if job["import_batch_id"] is not None:
                    cur.execute(
                        """
                        UPDATE imports
                        SET failed_files = failed_files + 1,
                            status = 'FAILED'::import_status,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (job["import_batch_id"],),
                    )
                conn.commit()
                self._record_outcome(
                    outcome="failed",
                    job_id=job["id"],
                    import_batch_id=job["import_batch_id"],
                    message=error_message,
                    image_id=None,
                )
                self.redis.publish("jobs:events", json.dumps({"job_id": job["id"], "status": "failed"}))

    def _register_near_duplicates(self, cur, processed: ProcessedImage) -> None:
        if not processed.perceptual_hash:
            return
        cur.execute("SELECT value FROM app_settings WHERE key = 'near_duplicate_hamming_threshold' LIMIT 1")
        row = cur.fetchone()
        try:
            threshold = max(int(row["value"]) if row else 6, 1)
        except (TypeError, ValueError):
            threshold = 6

        cur.execute(
            """
            SELECT id, perceptual_hash
            FROM images
            WHERE id != %s
              AND perceptual_hash IS NOT NULL
              AND LENGTH(perceptual_hash) = %s
            """,
            (processed.image_id, len(processed.perceptual_hash)),
        )
        candidates = cur.fetchall()
        for candidate in candidates:
            distance = sum(
                1
                for left, right in zip(processed.perceptual_hash, candidate["perceptual_hash"], strict=False)
                if left != right
            )
            if distance > threshold:
                continue
            left_id = min(processed.image_id, candidate["id"])
            right_id = max(processed.image_id, candidate["id"])
            cur.execute(
                """
                SELECT id
                FROM near_duplicate_reviews
                WHERE image_id = %s AND similar_image_id = %s
                """,
                (left_id, right_id),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO near_duplicate_reviews (
                    image_id,
                    similar_image_id,
                    hamming_distance,
                    status,
                    created_at,
                    updated_at
                ) VALUES (%s, %s, %s, %s, NOW(), NOW())
                """,
                (left_id, right_id, distance, NEAR_DUPLICATE_STATUS_OPEN),
            )

    def _drop_job_with_audit(self, job: dict, message: str, event_type: str, cur=None) -> None:
        if cur is None:
            with get_connection() as conn:
                with conn.cursor() as own_cur:
                    self._drop_job_with_audit(job, message, event_type, cur=own_cur)
                    conn.commit()
            return

        cur.execute(
            """
            INSERT INTO worker_audit_logs (job_id, import_batch_id, event_type, message, details, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                job["id"],
                job["import_batch_id"],
                event_type,
                message,
                json.dumps({"queue_path": job["queue_path"], "worker_id": self.worker_id}),
            ),
        )
        cur.execute("DELETE FROM jobs WHERE id = %s", (job["id"],))
        if job["import_batch_id"] is not None:
            self._reconcile_import(cur, job["import_batch_id"])
        self._record_outcome(
            outcome="failed",
            job_id=job["id"],
            import_batch_id=job["import_batch_id"],
            message=message,
            image_id=None,
        )
        self.redis.publish("jobs:events", json.dumps({"job_id": job["id"], "status": "dropped"}))

    def _reconcile_import(self, cur, import_batch_id: int) -> None:
        cur.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM jobs
            WHERE import_batch_id = %s
            GROUP BY status
            """,
            (import_batch_id,),
        )
        rows = cur.fetchall()
        if not rows:
            cur.execute("DELETE FROM imports WHERE id = %s", (import_batch_id,))
            return

        counts = {row["status"]: row["count"] for row in rows}
        total_files = sum(counts.values())
        processed_files = counts.get("done", 0)
        failed_files = counts.get("failed", 0)
        active_jobs = any(counts.get(status, 0) for status in ("queued", "running", "retrying"))

        if active_jobs:
            status = "RUNNING"
            finished_at_sql = "finished_at"
        elif failed_files:
            status = "FAILED"
            finished_at_sql = "NOW()"
        else:
            status = "DONE"
            finished_at_sql = "NOW()"

        cur.execute(
            f"""
            UPDATE imports
            SET total_files = %s,
                processed_files = %s,
                failed_files = %s,
                status = %s::import_status,
                finished_at = {finished_at_sql},
                updated_at = NOW()
            WHERE id = %s
            """,
            (total_files, processed_files, failed_files, status, import_batch_id),
        )

    def _prune_completed_job(self, cur, job_id: int, import_batch_id: int | None) -> None:
        cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        if import_batch_id is None:
            return

        cur.execute("SELECT COUNT(*) AS count FROM jobs WHERE import_batch_id = %s", (import_batch_id,))
        remaining_jobs = int(cur.fetchone()["count"])
        if remaining_jobs == 0:
            cur.execute("DELETE FROM imports WHERE id = %s", (import_batch_id,))

    def _record_outcome(
        self,
        outcome: str,
        job_id: int | None,
        import_batch_id: int | None,
        message: str,
        image_id: str | None,
    ) -> None:
        payload = json.dumps(
            {
                "job_id": job_id,
                "import_batch_id": import_batch_id,
                "outcome": outcome,
                "message": message,
                "image_id": image_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.redis.lpush(OUTCOME_STREAM_KEY, payload)
        self.redis.ltrim(OUTCOME_STREAM_KEY, 0, OUTCOME_STREAM_LIMIT - 1)


def _guess_mime(suffix: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".gif": "image/gif",
        ".webm": "video/webm",
    }.get(suffix, "application/octet-stream")
