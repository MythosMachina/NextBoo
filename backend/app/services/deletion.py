from pathlib import Path

from app.core.config import get_settings
from app.models.image import Image
from app.models.import_job import Job
from app.services.operations import sanitize_jobs_and_imports
from app.services.storage_sanitation import prune_empty_media_dirs
from app.services.tags import prune_orphan_tags
from sqlalchemy.orm import Session


def delete_image_assets(image: Image) -> None:
    settings = get_settings()
    removable_paths: set[Path] = set()
    for variant in image.variants:
        relative = variant.relative_path.lstrip("/")
        if relative.startswith("content/"):
            removable_paths.add(Path(settings.content_path).parent / relative)
        elif relative.startswith("content_thumbs/"):
            removable_paths.add(Path(settings.thumb_path).parent / relative)

    for file_path in removable_paths:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            continue


def hard_delete_image(db: Session, image: Image) -> None:
    affected_tag_ids = {image_tag.tag_id for image_tag in image.tags}
    delete_image_assets(image)
    db.query(Job).filter(Job.image_id == image.id).delete(synchronize_session=False)
    db.delete(image)
    db.flush()
    prune_orphan_tags(db, affected_tag_ids)
    sanitize_jobs_and_imports(db)
    prune_empty_media_dirs()
