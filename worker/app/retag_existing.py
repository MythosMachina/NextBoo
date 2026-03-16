from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from app.db import get_connection
from app.pipeline import (
    generate_motion_preview,
    is_animated_webp,
    predict_existing_animated_or_video,
    predict_existing_static_image,
)
from app.storage import StorageService
from app.settings import get_settings
from app.tagger import build_tagger, decide_rating


logger = logging.getLogger("worker.retag")

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
PREVIEW_VARIANT_ENUM = "PREVIEW"


def normalize_rule_rating(value: object) -> str:
    normalized = str(value).strip().lower()
    if normalized.startswith("rating."):
        normalized = normalized.split(".", 1)[1]
    return normalized


def apply_rating_rules(cur, prediction) -> None:
    present_tags = (
        set(prediction.general_tags)
        | set(prediction.character_tags)
        | set(prediction.copyright_tags)
        | set(prediction.artist_tags)
        | set(prediction.meta_tags)
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

    strongest_rule = prediction.rating
    rating_scores = {
        "general": float(prediction.rating_scores.get("general", 0.0)),
        "sensitive": float(prediction.rating_scores.get("sensitive", 0.0)),
        "questionable": float(prediction.rating_scores.get("questionable", 0.0)),
        "explicit": float(prediction.rating_scores.get("explicit", 0.0)),
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

    next_rating, next_score = decide_rating(rating_scores, prediction.general_tags)
    if RATING_ORDER.get(strongest_rule, 0) > RATING_ORDER.get(next_rating, 0):
        next_rating = strongest_rule
        next_score = max(next_score, rating_scores.get("questionable", 0.0), rating_scores.get("explicit", 0.0))

    prediction.rating = next_rating
    prediction.rating_score = next_score
    prediction.rating_scores = rating_scores


def upsert_tag(cur, name: str, display_name: str, category: str) -> int:
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
    return cur.fetchone()["id"]


def replace_auto_tags(cur, image_id: str, prediction) -> None:
    cur.execute(
        f"""
        DELETE FROM image_tags
        WHERE image_id = %s AND source = '{AUTO_TAG_SOURCE_ENUM}'::tag_source
        """,
        (image_id,),
    )

    all_tags = [
        ("general", name, score) for name, score in prediction.general_tags.items()
    ] + [
        ("character", name, score) for name, score in prediction.character_tags.items()
    ] + [
        ("copyright", name, score) for name, score in prediction.copyright_tags.items()
    ] + [
        ("artist", name, score) for name, score in prediction.artist_tags.items()
    ] + [
        ("meta", name, score) for name, score in prediction.meta_tags.items()
    ]

    for category, name, score in all_tags:
        tag_id = upsert_tag(cur, name, name, category)
        cur.execute(
            f"""
            INSERT INTO image_tags (image_id, tag_id, source, confidence, is_manual, created_at, updated_at)
            VALUES (%s, %s, '{AUTO_TAG_SOURCE_ENUM}'::tag_source, %s, FALSE, NOW(), NOW())
            ON CONFLICT (image_id, tag_id, source)
            DO UPDATE SET confidence = EXCLUDED.confidence, updated_at = NOW()
            """,
            (image_id, tag_id, score),
        )


def prune_orphan_tags(cur) -> None:
    cur.execute(
        """
        DELETE FROM tags
        WHERE name_normalized NOT IN ('image', 'animated')
          AND NOT EXISTS (
            SELECT 1 FROM image_tags it WHERE it.tag_id = tags.id
          )
        """
    )


def resolve_source_path(storage: StorageService, relative_path: str) -> Path:
    return storage.content_path.parent / relative_path


def predict_for_image(storage: StorageService, tagger, image_id: str, source_path: Path):
    workdir = storage.processing_path / f"retag_{image_id.replace('-', '')}"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        suffix = source_path.suffix.lower()
        if suffix in {".gif", ".webm"} or (suffix == ".webp" and is_animated_webp(source_path)):
            return predict_existing_animated_or_video(source_path, workdir, tagger)
        return predict_existing_static_image(source_path, tagger)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def retag_existing(limit: int | None = None, image_id: str | None = None) -> tuple[int, int]:
    storage = StorageService()
    storage.ensure_dirs()
    tagger = build_tagger()
    processed = 0
    failed = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT i.id, iv.relative_path
                FROM images i
                JOIN image_variants iv
                  ON iv.image_id = i.id
                 AND iv.variant_type = 'ORIGINAL'::variant_type
                ORDER BY i.created_at ASC
            """
            params: list[object] = []
            if image_id:
                query = """
                    SELECT i.id, iv.relative_path
                    FROM images i
                    JOIN image_variants iv
                      ON iv.image_id = i.id
                     AND iv.variant_type = 'ORIGINAL'::variant_type
                    WHERE i.id = %s
                """
                params = [image_id]
            elif limit is not None:
                query += " LIMIT %s"
                params = [limit]

            cur.execute(query, params)
            rows = cur.fetchall()

        for row in rows:
            try:
                source_path = resolve_source_path(storage, row["relative_path"])
                if not source_path.exists():
                    logger.warning("retag skipped missing source image_id=%s path=%s", row["id"], source_path)
                    failed += 1
                    continue
                prediction = predict_for_image(storage, tagger, row["id"], source_path)
                with conn.cursor() as cur:
                    apply_rating_rules(cur, prediction)
                    replace_auto_tags(cur, row["id"], prediction)
                    cur.execute(
                        """
                        UPDATE images
                        SET rating = %s::rating,
                            nsfw_score = %s,
                            auto_model_version = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (prediction.rating.upper(), prediction.rating_score, prediction.model_version, row["id"]),
                    )
                processed += 1
                if processed % 50 == 0:
                    with conn.cursor() as cur:
                        prune_orphan_tags(cur)
                    conn.commit()
                    logger.info("retag progress processed=%s failed=%s", processed, failed)
            except Exception:
                conn.rollback()
                failed += 1
                logger.exception("retag failed image_id=%s", row["id"])
                continue

        with conn.cursor() as cur:
            prune_orphan_tags(cur)
        conn.commit()

    return processed, failed


def backfill_preview_variants(limit: int | None = None, image_id: str | None = None) -> tuple[int, int]:
    storage = StorageService()
    storage.ensure_dirs()
    settings = get_settings()
    processed = 0
    failed = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT i.id, i.uuid_short, i.width, i.height, iv.relative_path
                FROM images i
                JOIN image_variants iv
                  ON iv.image_id = i.id
                 AND iv.variant_type = 'ORIGINAL'::variant_type
                LEFT JOIN image_variants pv
                  ON pv.image_id = i.id
                 AND pv.variant_type = 'PREVIEW'::variant_type
                WHERE pv.id IS NULL
                  AND EXISTS (
                    SELECT 1
                    FROM image_tags it
                    JOIN tags t ON t.id = it.tag_id
                    WHERE it.image_id = i.id
                      AND it.source = 'SYSTEM'::tag_source
                      AND t.name_normalized IN ('animated', 'video')
                  )
            """
            params: list[object] = []
            if image_id:
                query += " AND i.id = %s"
                params.append(image_id)
            query += " ORDER BY i.created_at ASC"
            if limit is not None and not image_id:
                query += " LIMIT %s"
                params.append(limit)

            cur.execute(query, params)
            rows = cur.fetchall()

        for row in rows:
            try:
                source_path = resolve_source_path(storage, row["relative_path"])
                if not source_path.exists():
                    logger.warning("preview backfill skipped missing source image_id=%s path=%s", row["id"], source_path)
                    failed += 1
                    continue

                preview_path = storage.preview_file(row["uuid_short"])
                preview_path.unlink(missing_ok=True)
                preview_width, preview_height, preview_size, preview_mime_type = generate_motion_preview(
                    source_path,
                    preview_path,
                    settings.thumb_max_edge,
                )
                if not preview_path.exists() or not preview_size or not preview_mime_type:
                    logger.warning("preview backfill could not generate preview image_id=%s path=%s", row["id"], source_path)
                    failed += 1
                    preview_path.unlink(missing_ok=True)
                    continue

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO image_variants (image_id, variant_type, relative_path, mime_type, file_size, width, height, created_at)
                        VALUES (%s, %s::variant_type, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            row["id"],
                            PREVIEW_VARIANT_ENUM,
                            str(preview_path.relative_to(storage.thumb_path.parent)),
                            preview_mime_type,
                            preview_size,
                            preview_width or min(row["width"], settings.thumb_max_edge),
                            preview_height or min(row["height"], settings.thumb_max_edge),
                        ),
                    )
                processed += 1
                if processed % 50 == 0:
                    conn.commit()
                    logger.info("preview backfill progress processed=%s failed=%s", processed, failed)
            except Exception:
                conn.rollback()
                failed += 1
                logger.exception("preview backfill failed image_id=%s", row["id"])
                continue

        conn.commit()

    return processed, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Retag existing images in place.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--image-id", type=str, default=None)
    args = parser.parse_args()

    processed, failed = retag_existing(limit=args.limit, image_id=args.image_id)
    print(f"retag_existing processed={processed} failed={failed}")


if __name__ == "__main__":
    main()
