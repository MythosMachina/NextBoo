import logging
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from app.db import get_connection
from app.pipeline import probe_media_metadata, probe_visual_dimensions
from app.settings import get_settings
from app.storage import StorageService
from redis import Redis


logger = logging.getLogger("worker.upload_pipeline")

MAX_FILE_SIZE = 100 * 1024 * 1024
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

SCAN_QUEUE = "upload:stage:scan"
DEDUPE_QUEUE = "upload:stage:dedupe"
NORMALIZE_QUEUE = "upload:stage:normalize"
DISPATCH_QUEUE = "upload:stage:dispatch"

STAGE_QUEUE_MAP = {
    "scanning": SCAN_QUEUE,
    "dedupe": DEDUPE_QUEUE,
    "normalize": NORMALIZE_QUEUE,
    "dispatch": DISPATCH_QUEUE,
}

NEXT_STAGE_MAP = {
    "scanning": "dedupe",
    "dedupe": "normalize",
    "normalize": "dispatch",
}

TERMINAL_STATUSES = {"duplicate", "rejected", "completed", "failed"}


class UploadPipelineService:
    def __init__(self, stage_name: str) -> None:
        if stage_name not in STAGE_QUEUE_MAP:
            raise ValueError(f"Unknown upload pipeline stage: {stage_name}")
        self.stage_name = stage_name
        self.queue_name = STAGE_QUEUE_MAP[stage_name]
        self.settings = get_settings()
        self.redis = Redis.from_url(self.settings.redis_dsn, decode_responses=True)
        self.storage = StorageService()
        self.worker_id = f"upload-{stage_name}-{Path('/etc/hostname').read_text().strip() if Path('/etc/hostname').exists() else 'local'}"
        self.presence_key = f"nextboo:upload-stage:{stage_name}:{self.worker_id}"

    def run_forever(self) -> None:
        self.storage.ensure_dirs()
        logger.info("upload pipeline stage runner started stage=%s queue=%s", self.stage_name, self.queue_name)
        while True:
            self.touch_presence()
            item = self.redis.blpop([self.queue_name], timeout=5)
            if not item:
                continue
            _queue_name, raw_item_id = item
            try:
                self.handle_item(int(raw_item_id))
            except Exception:
                logger.exception("upload pipeline stage failed stage=%s item_id=%s", self.stage_name, raw_item_id)

    def touch_presence(self) -> None:
        self.redis.set(
            self.presence_key,
            datetime.now(timezone.utc).isoformat(),
            ex=self.settings.worker_presence_ttl_seconds,
        )

    def handle_item(self, item_id: int) -> None:
        claimed = self._claim_item(item_id)
        if not claimed:
            return
        try:
            if self.stage_name == "scanning":
                self._handle_scan(claimed)
            elif self.stage_name == "dedupe":
                self._handle_dedupe(claimed)
            elif self.stage_name == "normalize":
                self._handle_normalize(claimed)
            else:
                self._handle_dispatch(claimed)
        except Exception as exc:
            self._mark_failed(claimed["id"], claimed["batch_id"], str(exc))

    def _claim_item(self, item_id: int) -> dict | None:
        expected_stage = "quarantine" if self.stage_name == "scanning" else self.stage_name
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE upload_pipeline_items
                    SET status = 'running',
                        stage = %s,
                        detail_message = %s,
                        last_stage_change_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND stage = %s
                      AND status IN ('received', 'queued', 'ready')
                    RETURNING id, batch_id, submitted_by_user_id, original_filename, detected_mime_type,
                              media_family, quarantine_path, normalized_path, checksum_sha256, source_size,
                              linked_import_id, linked_job_id, linked_image_id
                    """,
                    (self.stage_name, f"{self.stage_name} runner claimed item", item_id, expected_stage),
                )
                row = cur.fetchone()
                conn.commit()
        return row

    def _handle_scan(self, item: dict) -> None:
        source = Path(item["quarantine_path"] or "")
        if not source.exists():
            raise FileNotFoundError(f"Quarantine source missing: {source}")
        mime_type = item["detected_mime_type"] or mimetypes.guess_type(item["original_filename"])[0] or "application/octet-stream"
        if mime_type not in ALLOWED_MIME_TYPES:
            self._mark_rejected(item["id"], item["batch_id"], f"Unsupported MIME type: {mime_type}")
            return
        file_size = source.stat().st_size
        if file_size > MAX_FILE_SIZE:
            self._mark_rejected(item["id"], item["batch_id"], "File exceeds maximum size.")
            return

        media_family = "video" if mime_type.startswith("video/") else "image"
        if media_family == "image":
            with Image.open(source) as image:
                image.verify()
        else:
            dimensions = probe_visual_dimensions(source)
            if not all(dimensions):
                raise RuntimeError(f"Could not probe video dimensions for {source.name}")
            _metadata = probe_media_metadata(source)

        self._advance(item["id"], item["batch_id"], "dedupe", "queued", "Scan passed, queued for duplicate check.", mime_type=mime_type, media_family=media_family)

    def _handle_dedupe(self, item: dict) -> None:
        checksum = item["checksum_sha256"]
        if not checksum:
            raise RuntimeError("Missing checksum for duplicate check.")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM images WHERE checksum_sha256 = %s LIMIT 1", (checksum,))
                existing = cur.fetchone()
                if existing:
                    cur.execute(
                        """
                        UPDATE upload_pipeline_items
                        SET status = 'duplicate',
                            linked_image_id = %s,
                            detail_message = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (existing["id"], f"Duplicate of existing image {existing['id']}", item["id"]),
                    )
                    conn.commit()
                    self._sync_batch(item["batch_id"])
                    return

                cur.execute(
                    """
                    SELECT id
                    FROM upload_pipeline_items
                    WHERE batch_id = %s
                      AND checksum_sha256 = %s
                      AND id < %s
                      AND status NOT IN ('rejected', 'failed', 'duplicate')
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (item["batch_id"], checksum, item["id"]),
                )
                duplicate = cur.fetchone()
                if duplicate:
                    cur.execute(
                        """
                        UPDATE upload_pipeline_items
                        SET status = 'duplicate',
                            detail_message = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (f"Duplicate inside batch, matched item {duplicate['id']}", item["id"]),
                    )
                    conn.commit()
                    self._sync_batch(item["batch_id"])
                    return
                conn.commit()

        self._advance(item["id"], item["batch_id"], "normalize", "queued", "Duplicate check passed, queued for normalization.")

    def _handle_normalize(self, item: dict) -> None:
        source = Path(item["quarantine_path"] or "")
        if not source.exists():
            raise FileNotFoundError(f"Quarantine source missing: {source}")

        if (item["media_family"] or "image") == "image":
            with Image.open(source) as image:
                image.load()
        else:
            metadata = probe_media_metadata(source)
            if not metadata.get("video_codec"):
                raise RuntimeError(f"Video normalization probe failed for {source.name}")

        self._advance(
            item["id"],
            item["batch_id"],
            "dispatch",
            "ready",
            "Normalization passed, queued for dispatch.",
            normalized_path=str(source),
        )

    def _handle_dispatch(self, item: dict) -> None:
        source = Path(item["normalized_path"] or item["quarantine_path"] or "")
        if not source.exists():
            raise FileNotFoundError(f"Dispatch source missing: {source}")

        linked_import_id = self._ensure_import_batch(item["batch_id"], item["submitted_by_user_id"])
        target = self.storage.queue_path / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

        queue_name = "jobs:ingest:video" if item["media_family"] == "video" else "jobs:ingest:camie"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (job_type, queue_path, status, retry_count, max_retries, import_batch_id, created_at, updated_at)
                    VALUES ('INGEST'::job_type, %s, 'QUEUED'::job_status, 0, 3, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (str(target), linked_import_id),
                )
                job = cur.fetchone()
                cur.execute(
                    """
                    UPDATE upload_pipeline_items
                    SET stage = 'final_ingest',
                        status = 'dispatched',
                        linked_import_id = %s,
                        linked_job_id = %s,
                        detail_message = %s,
                        last_stage_change_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (linked_import_id, job["id"], f"Dispatched to {queue_name}", item["id"]),
                )
                cur.execute(
                    """
                    UPDATE imports
                    SET total_files = total_files + 1,
                        status = 'RUNNING'::import_status,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (linked_import_id,),
                )
                conn.commit()

        self.redis.rpush(queue_name, str(job["id"]))
        self._sync_batch(item["batch_id"])

    def _ensure_import_batch(self, batch_id: int, submitted_by_user_id: int | None) -> int:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT linked_import_id, source_name FROM upload_pipeline_batches WHERE id = %s", (batch_id,))
                batch = cur.fetchone()
                if not batch:
                    raise RuntimeError(f"Upload pipeline batch {batch_id} not found.")
                if batch["linked_import_id"] is not None:
                    conn.commit()
                    return batch["linked_import_id"]

                cur.execute(
                    """
                    INSERT INTO imports (source_type, source_name, submitted_by_user_id, total_files, processed_files, failed_files, status, created_at, updated_at)
                    VALUES ('WEB'::import_source_type, %s, %s, 0, 0, 0, 'PENDING'::import_status, NOW(), NOW())
                    RETURNING id
                    """,
                    (batch["source_name"], submitted_by_user_id),
                )
                import_row = cur.fetchone()
                cur.execute(
                    "UPDATE upload_pipeline_batches SET linked_import_id = %s, updated_at = NOW() WHERE id = %s",
                    (import_row["id"], batch_id),
                )
                conn.commit()
                return import_row["id"]

    def _advance(
        self,
        item_id: int,
        batch_id: int,
        next_stage: str,
        next_status: str,
        message: str,
        *,
        mime_type: str | None = None,
        media_family: str | None = None,
        normalized_path: str | None = None,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE upload_pipeline_items
                    SET stage = %s,
                        status = %s,
                        detected_mime_type = COALESCE(%s, detected_mime_type),
                        media_family = COALESCE(%s, media_family),
                        normalized_path = COALESCE(%s, normalized_path),
                        detail_message = %s,
                        last_stage_change_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (next_stage, next_status, mime_type, media_family, normalized_path, message, item_id),
                )
                conn.commit()
        self.redis.rpush(STAGE_QUEUE_MAP[next_stage], str(item_id))
        self._sync_batch(batch_id)

    def _mark_rejected(self, item_id: int, batch_id: int, message: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE upload_pipeline_items
                    SET status = 'rejected',
                        detail_message = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (message, item_id),
                )
                conn.commit()
        self._sync_batch(batch_id)

    def _mark_failed(self, item_id: int, batch_id: int, message: str) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE upload_pipeline_items
                    SET status = 'failed',
                        detail_message = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (message, item_id),
                )
                conn.commit()
        self._sync_batch(batch_id)

    def _sync_batch(self, batch_id: int) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM upload_pipeline_items
                    WHERE batch_id = %s
                    GROUP BY status
                    """,
                    (batch_id,),
                )
                rows = cur.fetchall()
                counts = {str(row["status"]): int(row["count"]) for row in rows}
                total_items = sum(counts.values())
                completed_items = counts.get("completed", 0)
                duplicate_items = counts.get("duplicate", 0)
                rejected_items = counts.get("rejected", 0)
                failed_items = counts.get("failed", 0)
                active_count = counts.get("received", 0) + counts.get("queued", 0) + counts.get("running", 0) + counts.get("ready", 0) + counts.get("dispatched", 0)
                if total_items and completed_items + duplicate_items + rejected_items + failed_items >= total_items:
                    batch_status = "completed" if failed_items == 0 else "failed"
                    finished_at = datetime.now(timezone.utc)
                elif active_count:
                    batch_status = "running"
                    finished_at = None
                else:
                    batch_status = "received"
                    finished_at = None
                cur.execute(
                    """
                    UPDATE upload_pipeline_batches
                    SET total_items = %s,
                        completed_items = %s,
                        duplicate_items = %s,
                        rejected_items = %s,
                        failed_items = %s,
                        status = %s,
                        finished_at = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        total_items,
                        completed_items,
                        duplicate_items,
                        rejected_items,
                        failed_items,
                        batch_status,
                        finished_at,
                        batch_id,
                    ),
                )
                conn.commit()
