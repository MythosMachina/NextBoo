from __future__ import annotations

from datetime import datetime, timezone

from app.core.constants import Rating, ReportStatus, VisibilityStatus
from app.models.image import Image, ImageTag
from app.models.moderation import ImageModeration, ImageReport
from app.models.tag import Tag, TagRatingRule
from app.models.user import User
from app.services.search import normalize_tag_token
from sqlalchemy.orm import Session, selectinload


RATING_RANK = {
    Rating.GENERAL: 0,
    Rating.SENSITIVE: 1,
    Rating.QUESTIONABLE: 2,
    Rating.EXPLICIT: 3,
}

DEFAULT_BOOSTS = {
    Rating.GENERAL: 0.18,
    Rating.SENSITIVE: 0.20,
    Rating.QUESTIONABLE: 0.24,
    Rating.EXPLICIT: 0.34,
}


def normalize_rating_value(value: Rating | str) -> Rating:
    if isinstance(value, Rating):
        return value
    normalized = str(value).strip().lower()
    if normalized.startswith("rating."):
        normalized = normalized.split(".", 1)[1]
    return Rating(normalized)


def get_or_create_rule_tag(db: Session, raw_name: str) -> Tag:
    normalized = normalize_tag_token(raw_name)
    if not normalized:
        raise ValueError("Tag names must not be empty")
    tag = db.query(Tag).filter(Tag.name_normalized == normalized).first()
    if tag:
        return tag
    tag = Tag(name_normalized=normalized, display_name=normalized)
    db.add(tag)
    db.flush()
    return tag


def load_rating_rule_map(db: Session) -> dict[str, tuple[Rating, float]]:
    rows = (
        db.query(Tag.name_normalized, TagRatingRule.target_rating, TagRatingRule.boost)
        .join(Tag, Tag.id == TagRatingRule.tag_id)
        .filter(TagRatingRule.is_enabled.is_(True))
        .all()
    )
    return {
        tag_name: (normalize_rating_value(target_rating), float(boost))
        for tag_name, target_rating, boost in rows
    }


def apply_rating_rule_overrides(
    *,
    base_rating: Rating | str,
    rating_scores: dict[str, float],
    present_tags: set[str],
    rule_map: dict[str, tuple[Rating, float]],
) -> tuple[Rating, dict[str, float]]:
    normalized_scores = {
        "general": float(rating_scores.get("general", 0.0)),
        "sensitive": float(rating_scores.get("sensitive", 0.0)),
        "questionable": float(rating_scores.get("questionable", 0.0)),
        "explicit": float(rating_scores.get("explicit", 0.0)),
    }
    strongest_rule = normalize_rating_value(base_rating)

    for tag_name in present_tags:
        rule = rule_map.get(tag_name)
        if not rule:
            continue
        target_rating, configured_boost = rule
        boost = configured_boost or DEFAULT_BOOSTS[target_rating]
        if target_rating == Rating.GENERAL:
            normalized_scores["general"] = min(1.0, normalized_scores["general"] + boost)
        elif target_rating == Rating.SENSITIVE:
            normalized_scores["sensitive"] = min(1.0, normalized_scores["sensitive"] + boost)
        elif target_rating == Rating.QUESTIONABLE:
            normalized_scores["questionable"] = min(1.0, normalized_scores["questionable"] + boost)
            normalized_scores["sensitive"] = min(1.0, normalized_scores["sensitive"] + (boost / 2))
        else:
            normalized_scores["explicit"] = min(1.0, normalized_scores["explicit"] + boost)
        if RATING_RANK[target_rating] > RATING_RANK[strongest_rule]:
            strongest_rule = target_rating

    return strongest_rule, normalized_scores


def floor_rating(base_rating: Rating | str, minimum_rating: Rating) -> Rating:
    current = normalize_rating_value(base_rating)
    return minimum_rating if RATING_RANK[minimum_rating] > RATING_RANK[current] else current


def reclassify_image_from_rules(db: Session, image: Image, rule_map: dict[str, tuple[Rating, float]]) -> bool:
    tag_names = {item.tag.name_normalized for item in image.tags if item.tag}
    current_rating = normalize_rating_value(image.rating)
    strongest_rule, rating_scores = apply_rating_rule_overrides(
        base_rating=current_rating,
        rating_scores={
            "general": 1.0 if current_rating == Rating.GENERAL else 0.0,
            "sensitive": 1.0 if current_rating == Rating.SENSITIVE else 0.0,
            "questionable": 1.0 if current_rating == Rating.QUESTIONABLE else 0.0,
            "explicit": 1.0 if current_rating == Rating.EXPLICIT else 0.0,
        },
        present_tags=tag_names,
        rule_map=rule_map,
    )
    next_rating = floor_rating(current_rating, strongest_rule)
    if current_rating == Rating.EXPLICIT and strongest_rule != Rating.EXPLICIT:
        next_rating = Rating.EXPLICIT
    elif current_rating == Rating.QUESTIONABLE and strongest_rule in {Rating.GENERAL, Rating.SENSITIVE}:
        next_rating = Rating.QUESTIONABLE
    elif current_rating == Rating.SENSITIVE and strongest_rule == Rating.GENERAL:
        next_rating = Rating.SENSITIVE
    elif strongest_rule == Rating.EXPLICIT or rating_scores["explicit"] >= 0.5:
        next_rating = Rating.EXPLICIT
    elif strongest_rule == Rating.QUESTIONABLE or rating_scores["questionable"] >= 0.5:
        next_rating = Rating.QUESTIONABLE
    elif strongest_rule == Rating.SENSITIVE or rating_scores["sensitive"] >= 0.5:
        next_rating = Rating.SENSITIVE
    else:
        next_rating = Rating.GENERAL
    if next_rating == current_rating:
        return False
    image.rating = next_rating
    db.add(image)
    return True


def reclassify_all_images_from_rules(db: Session) -> int:
    rule_map = load_rating_rule_map(db)
    if not rule_map:
        return 0
    images = (
        db.query(Image)
        .options(selectinload(Image.tags).selectinload(ImageTag.tag))
        .all()
    )
    changed = 0
    for image in images:
        if reclassify_image_from_rules(db, image, rule_map):
            changed += 1
    return changed


def resolve_open_reports_for_release(db: Session, image: Image, current_user: User, note: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    updated = (
        db.query(ImageReport)
        .filter(
            ImageReport.image_id == image.id,
            ImageReport.status.in_([ReportStatus.OPEN, ReportStatus.IN_REVIEW]),
        )
        .all()
    )
    for report in updated:
        report.status = ReportStatus.RESOLVED
        report.review_note = note or "released_from_moderation"
        report.reviewed_by_user_id = current_user.id
        report.reviewed_at = now
        db.add(report)

    moderation = image.moderation or ImageModeration(image_id=image.id)
    moderation.visibility_status = VisibilityStatus.VISIBLE
    moderation.reason = "released_after_review"
    moderation.note = note or "released_after_review"
    moderation.acted_by_user_id = current_user.id
    moderation.acted_at = now
    db.add(moderation)
    return len(updated)
