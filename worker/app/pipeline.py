import logging
import json
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


class SourceFileMissingError(FileNotFoundError):
    pass


class AnalysisFrameGenerationError(RuntimeError):
    pass


@dataclass
class ProcessedImage:
    image_id: str
    uuid_short: str
    width: int
    height: int
    duration_seconds: float | None
    frame_rate: float | None
    has_audio: bool
    video_codec: str | None
    audio_codec: str | None
    aspect_ratio: float
    source_hash: str
    perceptual_hash: str
    original_path: Path
    thumb_path: Path
    preview_path: Path | None
    original_size: int
    thumb_size: int
    preview_size: int | None
    preview_width: int | None
    preview_height: int | None
    preview_mime_type: str | None
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


def probe_visual_dimensions(source_path: Path) -> tuple[int | None, int | None]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(source_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        raw = result.stdout.strip()
        if not raw or "x" not in raw:
            return None, None
        width_raw, height_raw = raw.split("x", 1)
        return int(width_raw), int(height_raw)
    except Exception:
        return None, None


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
        raise AnalysisFrameGenerationError(f"Expected extracted frame at {target_path}")

    with Image.open(target_path) as image:
        return image.width, image.height


def extract_frame_to_png_with_retries(
    source_path: Path,
    target_path: Path,
    position_ratio: float,
    *,
    max_attempts: int = 3,
) -> tuple[int, int]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            target_path.unlink(missing_ok=True)
            return extract_frame_to_png(source_path, target_path, position_ratio)
        except AnalysisFrameGenerationError as exc:
            last_error = exc
            logger.warning(
                "analysis frame generation retry source=%s frame=%s attempt=%s/%s",
                source_path,
                target_path.name,
                attempt,
                max_attempts,
            )
            target_path.unlink(missing_ok=True)
            continue
    raise AnalysisFrameGenerationError(str(last_error) if last_error else f"Expected extracted frame at {target_path}")


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


def probe_media_metadata(source_path: Path) -> dict[str, object]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(source_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout or "{}")
    except Exception:
        return {
            "duration_seconds": None,
            "frame_rate": None,
            "has_audio": False,
            "video_codec": None,
            "audio_codec": None,
        }

    streams = payload.get("streams", [])
    format_section = payload.get("format", {})
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    duration_raw = format_section.get("duration") or (video_stream or {}).get("duration")
    try:
        duration_seconds = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration_seconds = None

    avg_frame_rate = (video_stream or {}).get("avg_frame_rate")
    frame_rate = None
    if avg_frame_rate and avg_frame_rate != "0/0":
        try:
            numerator, denominator = avg_frame_rate.split("/", 1)
            frame_rate = float(numerator) / float(denominator)
        except Exception:
            frame_rate = None

    return {
        "duration_seconds": duration_seconds,
        "frame_rate": frame_rate,
        "has_audio": audio_stream is not None,
        "video_codec": (video_stream or {}).get("codec_name"),
        "audio_codec": (audio_stream or {}).get("codec_name"),
    }


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
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
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
    preview_path: Path,
    workdir: Path,
    thumb_max_edge: int,
    tagger: Tagger,
) -> tuple[int, int, str, TagPrediction, int | None, int | None, int | None, str | None]:
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
    preview_width, preview_height, preview_size, preview_mime_type = generate_motion_preview(local_input, preview_path, thumb_max_edge)
    return width, height, perceptual_hash, tag_prediction, preview_width, preview_height, preview_size, preview_mime_type


def generate_motion_preview(
    source_path: Path,
    target_path: Path,
    max_edge: int,
) -> tuple[int | None, int | None, int | None, str | None]:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    scale_filter = (
        f"fps=10,scale='if(gt(iw,ih),min(iw,{max_edge}),-2)':'if(gt(iw,ih),-2,min(ih,{max_edge}))':flags=lanczos"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-an",
        "-t",
        "3",
        "-vf",
        scale_filter,
        "-c:v",
        "libvpx-vp9",
        "-b:v",
        "0",
        "-crf",
        "40",
        str(target_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        target_path.unlink(missing_ok=True)
        return None, None, None, None
    if not target_path.exists():
        return None, None, None, None
    width, height = probe_visual_dimensions(target_path)
    return width, height, target_path.stat().st_size, "video/webm"


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
        extract_frame_to_png_with_retries(local_input, frame_path, position_ratio)
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
    if not source_path.exists():
        raise SourceFileMissingError(f"Missing source file at {source_path}")
    workdir = storage.job_workdir(job_id)
    workdir.mkdir(parents=True, exist_ok=True)

    local_input = workdir / source_path.name
    if source_path.resolve() != local_input.resolve():
        shutil.copy2(source_path, local_input)

    full_uuid = str(uuid4())
    uuid_short = storage.derive_uuid_short(full_uuid)
    storage.prepare_variant_dirs(uuid_short)
    source_suffix = source_path.suffix.lower()
    is_video = source_suffix in {".webm", ".mp4", ".mkv"}
    treat_as_animated = source_suffix == ".gif" or (source_suffix == ".webp" and is_animated_webp(local_input))
    treat_as_motion = is_video or treat_as_animated
    storage_ext = source_suffix.lstrip(".") if treat_as_motion else "png"
    original_mime_type = original_mime_for_suffix(source_suffix if treat_as_motion else ".png")
    original_path = storage.content_file(uuid_short, storage_ext)
    thumb_path = storage.thumb_file(uuid_short)
    preview_path = storage.preview_file(uuid_short) if treat_as_motion else None
    media_metadata = probe_media_metadata(local_input) if treat_as_motion else {
        "duration_seconds": None,
        "frame_rate": None,
        "has_audio": False,
        "video_codec": None,
        "audio_codec": None,
    }
    if treat_as_motion:
        width, height, perceptual_hash, tag_prediction, preview_width, preview_height, preview_size, preview_mime_type = process_animated_or_video(
            local_input, original_path, thumb_path, preview_path, workdir, thumb_max_edge, tagger
        )
    else:
        width, height, perceptual_hash, tag_prediction = process_static_image(
            local_input, original_path, thumb_path, thumb_max_edge, tagger
        )
        preview_width = None
        preview_height = None
        preview_size = None
        preview_mime_type = None
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
        duration_seconds=media_metadata["duration_seconds"],
        frame_rate=media_metadata["frame_rate"],
        has_audio=bool(media_metadata["has_audio"]),
        video_codec=media_metadata["video_codec"],
        audio_codec=media_metadata["audio_codec"],
        aspect_ratio=round(width / height, 4) if height else 1.0,
        source_hash=source_hash,
        perceptual_hash=perceptual_hash,
        original_path=original_path,
        thumb_path=thumb_path,
        preview_path=preview_path,
        original_size=original_path.stat().st_size,
        thumb_size=thumb_path.stat().st_size,
        preview_size=preview_size,
        preview_width=preview_width,
        preview_height=preview_height,
        preview_mime_type=preview_mime_type,
        storage_ext=storage_ext,
        original_mime_type=original_mime_type,
        processed_at=processed_at,
        tag_prediction=tag_prediction,
        media_kind="video" if is_video else "animated" if treat_as_animated else "image",
    )
