import hashlib
import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from fastapi import UploadFile


def derive_uuid_short(full_uuid: str) -> str:
    return full_uuid.replace("-", "")[:16]


class StorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.queue_path = Path(settings.queue_path)
        self.processing_path = Path(settings.processing_path)
        self.processing_failed_path = Path(settings.processing_failed_path)
        self.content_path = Path(settings.content_path)
        self.thumb_path = Path(settings.thumb_path)
        self.import_path = Path(settings.import_path)

    def ensure_dirs(self) -> None:
        for path in (
            self.queue_path,
            self.processing_path,
            self.processing_failed_path,
            self.content_path,
            self.thumb_path,
            self.import_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def write_upload_to_queue(self, upload: UploadFile) -> tuple[str, str]:
        self.ensure_dirs()
        file_uuid = str(uuid4())
        safe_name = Path(upload.filename or "upload.bin").name
        ext = Path(safe_name).suffix.lower() or ".bin"
        queue_name = f"{file_uuid}{ext}"
        target = self.queue_path / queue_name
        hasher = hashlib.sha256()

        with target.open("wb") as destination:
            upload.file.seek(0)
            while chunk := upload.file.read(1024 * 1024):
                hasher.update(chunk)
                destination.write(chunk)

        return str(target), hasher.hexdigest()

    def move_to_failed(self, source_path: str) -> str:
        self.ensure_dirs()
        source = Path(source_path)
        target = self.processing_failed_path / source.name
        shutil.move(str(source), str(target))
        return str(target)
