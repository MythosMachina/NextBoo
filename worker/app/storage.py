import hashlib
import shutil
from pathlib import Path

from app.settings import get_settings


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.queue_path = Path(settings.queue_path)
        self.quarantine_path = Path(settings.quarantine_path)
        self.processing_path = Path(settings.processing_path)
        self.processing_failed_path = Path(settings.processing_failed_path)
        self.content_path = Path(settings.content_path)
        self.thumb_path = Path(settings.thumb_path)
        self.model_path = Path(settings.model_path)

    def ensure_dirs(self) -> None:
        for path in (
            self.quarantine_path,
            self.queue_path,
            self.processing_path,
            self.processing_failed_path,
            self.content_path,
            self.thumb_path,
            self.model_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def quarantine_file(self, filename: str) -> Path:
        return self.quarantine_path / filename

    @staticmethod
    def derive_uuid_short(full_uuid: str) -> str:
        return full_uuid.replace("-", "")[:16]

    @staticmethod
    def shard_for(short_id: str) -> str:
        return short_id[:2]

    def content_file(self, short_id: str, ext: str = "png") -> Path:
        normalized_ext = ext.lower().lstrip(".") or "bin"
        return self.content_path / self.shard_for(short_id) / f"{short_id}.{normalized_ext}"

    def thumb_file(self, short_id: str) -> Path:
        return self.thumb_path / self.shard_for(short_id) / f"{short_id}.webp"

    def preview_file(self, short_id: str) -> Path:
        return self.thumb_path / self.shard_for(short_id) / f"{short_id}-preview.webm"

    def prepare_variant_dirs(self, short_id: str) -> None:
        self.content_file(short_id).parent.mkdir(parents=True, exist_ok=True)
        self.thumb_file(short_id).parent.mkdir(parents=True, exist_ok=True)

    def job_workdir(self, job_id: int) -> Path:
        return self.processing_path / f"job_{job_id}"

    def remove_job_workdir(self, job_id: int) -> None:
        shutil.rmtree(self.job_workdir(job_id), ignore_errors=True)

    def move_to_failed(self, source: Path) -> Path:
        self.processing_failed_path.mkdir(parents=True, exist_ok=True)
        target = self.processing_failed_path / source.name
        shutil.move(str(source), str(target))
        return target

    @staticmethod
    def sha256_for_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
