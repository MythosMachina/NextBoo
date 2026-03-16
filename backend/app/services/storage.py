import hashlib
import mimetypes
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from fastapi import UploadFile


def derive_uuid_short(full_uuid: str) -> str:
    return full_uuid.replace("-", "")[:16]


class StorageService:
    max_zip_members = 2000
    max_zip_extract_size = 1024 * 1024 * 1024

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

    def stage_local_file_to_queue(self, source_path: Path) -> tuple[str, str]:
        self.ensure_dirs()
        file_uuid = str(uuid4())
        ext = source_path.suffix.lower() or ".bin"
        queue_name = f"{file_uuid}{ext}"
        target = self.queue_path / queue_name
        hasher = hashlib.sha256()

        with source_path.open("rb") as source, target.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                hasher.update(chunk)
                destination.write(chunk)

        return str(target), hasher.hexdigest()

    def list_import_sources(self) -> dict[str, list[str]]:
        self.ensure_dirs()
        folders: list[str] = []
        zip_archives: list[str] = []
        for child in sorted(self.import_path.iterdir(), key=lambda item: item.name.lower()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                folders.append(child.name)
            elif child.is_file() and child.suffix.lower() == ".zip":
                zip_archives.append(child.name)
        return {"folders": folders, "zip_archives": zip_archives}

    def iter_importable_files(self, root_path: Path) -> list[Path]:
        return [
            path
            for path in sorted(root_path.rglob("*"), key=lambda item: item.as_posix().lower())
            if path.is_file() and (mimetypes.guess_type(path.name)[0] or "").startswith(("image/", "video/"))
        ]

    def safe_extract_zip(self, zip_path: Path, target_dir: Path) -> list[Path]:
        self.ensure_dirs()
        target_root = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        extracted_files: list[Path] = []
        total_uncompressed = 0
        with zipfile.ZipFile(zip_path) as archive:
            for member_index, member in enumerate(archive.infolist(), start=1):
                if member_index > self.max_zip_members:
                    break
                member_name = member.filename.replace("\\", "/")
                if member.is_dir() or member_name.startswith("/") or ".." in Path(member_name).parts:
                    continue
                total_uncompressed += max(member.file_size, 0)
                if total_uncompressed > self.max_zip_extract_size:
                    break
                destination = (target_dir / member_name).resolve()
                if target_root not in destination.parents and destination != target_root:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
                extracted_files.append(destination)
        return extracted_files

    def move_to_failed(self, source_path: str) -> str:
        self.ensure_dirs()
        source = Path(source_path)
        target = self.processing_failed_path / source.name
        shutil.move(str(source), str(target))
        return str(target)
