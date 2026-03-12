from pathlib import Path

from app.core.constants import JobStatus
from app.core.config import get_settings
from app.models.image import ImageVariant
from app.models.import_job import Job
from app.services.tags import prune_orphan_tags
from sqlalchemy.orm import Session


def sanitize_gallery_storage(db: Session) -> dict[str, int]:
    settings = get_settings()
    content_root = Path(settings.content_path)
    thumb_root = Path(settings.thumb_path)
    queue_root = Path(settings.queue_path)
    failed_root = Path(settings.processing_failed_path)
    processing_root = Path(settings.processing_path)

    referenced_media = {relative_path for (relative_path,) in db.query(ImageVariant.relative_path).all()}
    referenced_job_names = {Path(queue_path).name for (queue_path,) in db.query(Job.queue_path).all()}
    active_job_ids = {
        job_id
        for (job_id,) in db.query(Job.id)
        .filter(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING]))
        .all()
    }

    removed_media_files = _remove_unreferenced_media_files(content_root, referenced_media)
    removed_media_files += _remove_unreferenced_media_files(thumb_root, referenced_media)
    removed_queue_files = _remove_unreferenced_job_files(queue_root, referenced_job_names)
    removed_failed_files = _remove_unreferenced_job_files(failed_root, referenced_job_names)
    removed_workdirs = _remove_stale_workdirs(processing_root, active_job_ids)
    removed_empty_dirs = _remove_empty_dirs([content_root, thumb_root, processing_root])
    removed_tags = prune_orphan_tags(db)

    return {
        "removed_media_files": removed_media_files,
        "removed_queue_files": removed_queue_files,
        "removed_failed_files": removed_failed_files,
        "removed_workdirs": removed_workdirs,
        "removed_empty_dirs": removed_empty_dirs,
        "removed_tags": removed_tags,
    }


def prune_empty_media_dirs() -> int:
    settings = get_settings()
    return _remove_empty_dirs([Path(settings.content_path), Path(settings.thumb_path)])


def _remove_unreferenced_media_files(root: Path, referenced_media: set[str]) -> int:
    if not root.exists():
        return 0
    removed = 0
    base_root = root.parent
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative_path = candidate.relative_to(base_root).as_posix()
        if relative_path in referenced_media:
            continue
        candidate.unlink(missing_ok=True)
        removed += 1
    return removed


def _remove_unreferenced_job_files(root: Path, referenced_job_names: set[str]) -> int:
    if not root.exists():
        return 0
    removed = 0
    for candidate in root.iterdir():
        if not candidate.is_file():
            continue
        if candidate.name in referenced_job_names:
            continue
        candidate.unlink(missing_ok=True)
        removed += 1
    return removed


def _remove_stale_workdirs(root: Path, active_job_ids: set[int]) -> int:
    if not root.exists():
        return 0
    removed = 0
    for candidate in root.iterdir():
        if not candidate.is_dir() or not candidate.name.startswith("job_"):
            continue
        try:
            job_id = int(candidate.name.removeprefix("job_"))
        except ValueError:
            continue
        if job_id in active_job_ids:
            continue
        for child in sorted(candidate.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        candidate.rmdir()
        removed += 1
    return removed


def _remove_empty_dirs(roots: list[Path]) -> int:
    removed = 0
    for root in roots:
        if not root.exists():
            continue
        for candidate in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
            try:
                candidate.rmdir()
            except OSError:
                continue
            removed += 1
    return removed
