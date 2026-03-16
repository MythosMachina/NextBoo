from __future__ import annotations

import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.constants import ProcessingStatus, UserRole, VariantType
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.backup_export import BackupExport
from app.models.image import Image, ImageVariant
from app.models.user import User
from sqlalchemy.orm import Session, selectinload


settings = get_settings()
EXPORT_ROOT = Path(settings.import_path) / "backup_exports"


def ensure_backup_export_directory() -> None:
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)


def list_backup_exports_for_user(db: Session, user: User) -> list[BackupExport]:
    return (
        db.query(BackupExport)
        .filter(BackupExport.user_id == user.id)
        .order_by(BackupExport.created_at.desc(), BackupExport.id.desc())
        .all()
    )


def queue_backup_export(db: Session, user: User) -> tuple[BackupExport, bool]:
    existing = (
        db.query(BackupExport)
        .filter(
            BackupExport.user_id == user.id,
            BackupExport.status.in_(["pending", "running"]),
        )
        .order_by(BackupExport.created_at.desc(), BackupExport.id.desc())
        .first()
    )
    if existing:
        return existing, False

    export = BackupExport(
        user_id=user.id,
        status="pending",
        current_message="Queued for low-priority ZIP creation.",
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return export, True


def _absolute_original_path(relative_path: str) -> Path:
    normalized = relative_path.lstrip("/")
    if normalized.startswith("content/"):
        return Path(settings.content_path) / normalized.removeprefix("content/")
    return Path("/app") / normalized


def _collect_user_originals(db: Session, user_id: int) -> list[tuple[Image, ImageVariant]]:
    images = (
        db.query(Image)
        .options(selectinload(Image.variants))
        .filter(Image.uploaded_by_user_id == user_id)
        .filter(Image.processing_status == ProcessingStatus.READY)
        .order_by(Image.created_at.asc(), Image.id.asc())
        .all()
    )
    items: list[tuple[Image, ImageVariant]] = []
    for image in images:
        original = next((variant for variant in image.variants if variant.variant_type == VariantType.ORIGINAL), None)
        if original:
            items.append((image, original))
    return items


def _build_archive_name(username: str, export_id: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_username = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in username).strip("_") or "user"
    return f"{safe_username}-backup-{export_id}-{stamp}.zip"


def _unique_zip_entry_name(image: Image, original: ImageVariant, used_names: set[str]) -> str:
    original_name = image.original_filename or f"{image.uuid_short}{Path(original.relative_path).suffix}"
    candidate = original_name
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    stem = Path(original_name).stem
    suffix = Path(original_name).suffix
    candidate = f"{stem}-{image.uuid_short}{suffix}"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = f"{stem}-{image.uuid_short}-{index}{suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def _mark_export_failed(db: Session, export: BackupExport, message: str) -> None:
    export.status = "failed"
    export.error_summary = message
    export.current_message = message
    export.finished_at = datetime.now(timezone.utc)
    db.add(export)
    db.commit()


def process_backup_export(db: Session, export: BackupExport) -> None:
    ensure_backup_export_directory()
    user = db.get(User, export.user_id)
    if not user:
        _mark_export_failed(db, export, "User no longer exists.")
        return

    export.status = "running"
    export.started_at = datetime.now(timezone.utc)
    export.finished_at = None
    export.error_summary = None
    export.current_message = "Collecting uploaded files."
    db.add(export)
    db.commit()
    db.refresh(export)

    items = _collect_user_originals(db, user.id)
    archive_name = _build_archive_name(user.username, export.id)
    archive_relative_path = f"backup_exports/{archive_name}"
    archive_path = EXPORT_ROOT / archive_name
    temp_path = archive_path.with_suffix(".zip.part")

    if archive_path.exists():
        archive_path.unlink()
    if temp_path.exists():
        temp_path.unlink()

    try:
        used_names: set[str] = set()
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for index, (image, original) in enumerate(items, start=1):
                absolute_path = _absolute_original_path(original.relative_path)
                if not absolute_path.exists() or not absolute_path.is_file():
                    continue
                archive.write(absolute_path, arcname=_unique_zip_entry_name(image, original, used_names))
                if index == 1 or index % 25 == 0:
                    export.current_message = f"Packing file {index} of {len(items)}."
                    export.item_count = index
                    db.add(export)
                    db.commit()
                time.sleep(0.03)

        os.replace(temp_path, archive_path)
        export.status = "done"
        export.zip_relative_path = archive_relative_path
        export.file_size = archive_path.stat().st_size
        export.item_count = len(used_names)
        export.current_message = "ZIP export ready."
        export.finished_at = datetime.now(timezone.utc)
        db.add(export)
        db.commit()
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        _mark_export_failed(db, export, str(exc))


def backup_export_worker_loop(stop_event) -> None:
    ensure_backup_export_directory()
    while not stop_event.is_set():
        with SessionLocal() as db:
            export = (
                db.query(BackupExport)
                .filter(BackupExport.status == "pending")
                .order_by(BackupExport.created_at.asc(), BackupExport.id.asc())
                .first()
            )
            if not export:
                stop_event.wait(5)
                continue
            process_backup_export(db, export)
        stop_event.wait(2)


def reactivate_tos_account(db: Session, user: User) -> User:
    if user.role != UserRole.TOS_DEACTIVATED:
        return user

    restore_role = user.tos_restore_role or UserRole.UPLOADER.value
    try:
        user.role = UserRole(restore_role)
    except ValueError:
        user.role = UserRole.UPLOADER
    user.can_upload = bool(user.tos_restore_can_upload)
    user.can_view_questionable = True if user.tos_restore_can_view_questionable is None else bool(user.tos_restore_can_view_questionable)
    user.can_view_explicit = bool(user.tos_restore_can_view_explicit)
    user.accepted_tos_at = None
    user.accepted_tos_version = None
    user.tos_declined_at = None
    user.tos_delete_after_at = None
    user.tos_restore_role = None
    user.tos_restore_can_upload = None
    user.tos_restore_can_view_questionable = None
    user.tos_restore_can_view_explicit = None
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
