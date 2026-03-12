import logging
import subprocess
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import imagehash
from PIL import Image, ImageOps

from app.storage import StorageService
from app.tagger import TagPrediction, Tagger, merge_predictions


logger = logging.getLogger("worker.pipeline")


@dataclass
class ProcessedImage:
    image_id: str
    uuid_short: str
    width: int
    height: int
    aspect_ratio: float
    source_hash: str
    perceptual_hash: str
    original_path: Path
    thumb_path: Path
    original_size: int
    thumb_size: int
    storage_ext: str
    original_mime_type: str
    processed_at: datetime
    tag_prediction: TagPrediction
    media_kind: str


def normalize_to_png(source_path: Path, target_path: Path) -> tuple[int, int]:
    with Image.open(source_path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGBA")
        normalized.save(target_path, format="PNG")
        return normalized.width, normalized.height


def generate_thumbnail(source_png: Path, target_webp: Path, max_edge: int) -> tuple[int, int]:
    with Image.open(source_png) as image:
        image.thumbnail((max_edge, max_edge))
        image.save(target_webp, format="WEBP", quality=85, method=6)
        return image.width, image.height


def compute_perceptual_hash(source_png: Path) -> str:
    with Image.open(source_png) as image:
        return str(imagehash.phash(image))


def is_animated_webp(source_path: Path) -> bool:
    try:
        with Image.open(source_path) as image:
            return bool(getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1)
    except OSError:
        return False


def extract_frame_to_png(source_path: Path, target_path: Path, position_ratio: float) -> tuple[int, int]:
    duration = probe_duration(source_path)
    if duration > 0 and position_ratio >= 1.0:
        timestamp = max(duration - 0.050, 0.0)
    else:
        timestamp = max(duration * min(position_ratio, 0.995), 0.0)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(source_path),
        "-frames:v",
        "1",
        str(target_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        if source_path.suffix.lower() in {".gif", ".webp"}:
            return extract_frame_with_pillow(source_path, target_path, position_ratio)
        fallback_command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            str(target_path),
        ]
        subprocess.run(fallback_command, check=True, capture_output=True, text=True)

    if not target_path.exists():
        if source_path.suffix.lower() in {".gif", ".webp"}:
            return extract_frame_with_pillow(source_path, target_path, position_ratio)
        raise FileNotFoundError(f"Expected extracted frame at {target_path}")

    with Image.open(target_path) as image:
        return image.width, image.height


def extract_mid_frame_with_pillow(source_path: Path, target_path: Path) -> tuple[int, int]:
    return extract_frame_with_pillow(source_path, target_path, 0.5)


def extract_frame_with_pillow(source_path: Path, target_path: Path, position_ratio: float) -> tuple[int, int]:
    with Image.open(source_path) as image:
        frame_count = max(int(getattr(image, "n_frames", 1)), 1)
        frame_index = min(max(round((frame_count - 1) * position_ratio), 0), frame_count - 1)
        image.seek(frame_index)
        extracted = ImageOps.exif_transpose(image).convert("RGBA")
        extracted.save(target_path, format="PNG")
        return extracted.width, extracted.height


def probe_duration(source_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(source_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(result.stdout.strip() or "0")
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def original_mime_for_suffix(suffix: str) -> str:
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


def process_static_image(
    local_input: Path,
    normalized_path: Path,
    thumb_path: Path,
    thumb_max_edge: int,
    tagger: Tagger,
) -> tuple[int, int, str, TagPrediction]:
    width, height = normalize_to_png(local_input, normalized_path)
    generate_thumbnail(normalized_path, thumb_path, thumb_max_edge)
    perceptual_hash = compute_perceptual_hash(normalized_path)
    tag_prediction = tagger.predict(normalized_path)
    return width, height, perceptual_hash, tag_prediction


def predict_existing_static_image(local_input: Path, tagger: Tagger) -> TagPrediction:
    return tagger.predict(local_input)


def process_animated_or_video(
    local_input: Path,
    original_path: Path,
    thumb_path: Path,
    workdir: Path,
    thumb_max_edge: int,
    tagger: Tagger,
) -> tuple[int, int, str, TagPrediction]:
    shutil.copy2(local_input, original_path)
    frame_positions = [0.0, 0.25, 0.5, 0.75, 1.0]
    extracted_frames: list[Path] = []
    predictions: list[TagPrediction] = []
    width = 0
    height = 0

    for index, position_ratio in enumerate(frame_positions):
        frame_path = workdir / f"analysis_frame_{index}.png"
        current_width, current_height = extract_frame_to_png(local_input, frame_path, position_ratio)
        if index == 2:
            generate_thumbnail(frame_path, thumb_path, thumb_max_edge)
            width, height = current_width, current_height
        extracted_frames.append(frame_path)
        predictions.append(tagger.predict(frame_path))

    perceptual_hash = compute_perceptual_hash(extracted_frames[2])
    tag_prediction = merge_predictions(predictions)
    for extracted_frame in extracted_frames:
        extracted_frame.unlink(missing_ok=True)
    return width, height, perceptual_hash, tag_prediction


def predict_existing_animated_or_video(
    local_input: Path,
    workdir: Path,
    tagger: Tagger,
) -> TagPrediction:
    frame_positions = [0.0, 0.25, 0.5, 0.75, 1.0]
    extracted_frames: list[Path] = []
    predictions: list[TagPrediction] = []

    for index, position_ratio in enumerate(frame_positions):
        frame_path = workdir / f"analysis_frame_{index}.png"
        extract_frame_to_png(local_input, frame_path, position_ratio)
        extracted_frames.append(frame_path)
        predictions.append(tagger.predict(frame_path))

    merged = merge_predictions(predictions)
    for extracted_frame in extracted_frames:
        extracted_frame.unlink(missing_ok=True)
    return merged


def process_image(
    job_id: int,
    queue_path: str,
    thumb_max_edge: int,
    storage: StorageService,
    tagger: Tagger,
) -> ProcessedImage:
    storage.ensure_dirs()
    source_path = Path(queue_path)
    workdir = storage.job_workdir(job_id)
    workdir.mkdir(parents=True, exist_ok=True)

    local_input = workdir / source_path.name
    if source_path.resolve() != local_input.resolve():
        shutil.copy2(source_path, local_input)

    full_uuid = str(uuid4())
    uuid_short = storage.derive_uuid_short(full_uuid)
    storage.prepare_variant_dirs(uuid_short)
    source_suffix = source_path.suffix.lower()
    treat_as_animated = source_suffix in {".gif", ".webm"} or (source_suffix == ".webp" and is_animated_webp(local_input))
    storage_ext = source_suffix.lstrip(".") if treat_as_animated else "png"
    original_mime_type = original_mime_for_suffix(source_suffix if treat_as_animated else ".png")
    original_path = storage.content_file(uuid_short, storage_ext)
    thumb_path = storage.thumb_file(uuid_short)
    if treat_as_animated:
        width, height, perceptual_hash, tag_prediction = process_animated_or_video(
            local_input, original_path, thumb_path, workdir, thumb_max_edge, tagger
        )
    else:
        width, height, perceptual_hash, tag_prediction = process_static_image(
            local_input, original_path, thumb_path, thumb_max_edge, tagger
        )
    with Image.open(thumb_path) as thumb_image:
        thumb_width, thumb_height = thumb_image.width, thumb_image.height
    source_hash = storage.sha256_for_file(local_input)
    processed_at = datetime.now(timezone.utc)

    logger.info(
        "processed image job=%s width=%s height=%s thumb=%sx%s",
        job_id,
        width,
        height,
        thumb_width,
        thumb_height,
    )

    return ProcessedImage(
        image_id=full_uuid,
        uuid_short=uuid_short,
        width=width,
        height=height,
        aspect_ratio=round(width / height, 4) if height else 1.0,
        source_hash=source_hash,
        perceptual_hash=perceptual_hash,
        original_path=original_path,
        thumb_path=thumb_path,
        original_size=original_path.stat().st_size,
        thumb_size=thumb_path.stat().st_size,
        storage_ext=storage_ext,
        original_mime_type=original_mime_type,
        processed_at=processed_at,
        tag_prediction=tag_prediction,
        media_kind="animated" if treat_as_animated else "image",
    )
