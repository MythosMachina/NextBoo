from datetime import datetime, timezone
from typing import Annotated

from app.api.deps import DbSession, get_current_user, get_optional_current_user
from app.core.constants import ProcessingStatus, Rating, TagCategory, TagSource, UserRole, VisibilityStatus
from app.models.image import Image, ImageTag
from app.models.moderation import ImageModeration, ImageReport
from app.models.tag import Tag
from app.models.user import User
from app.schemas.image import ImageDetail, ImageDetailResponse, ImageListItem, ImageListResponse
from app.schemas.moderation import ImageMetadataUpdate, ImageReportCreate, ImageVisibilityUpdate
from app.services.media import build_media_url, thumb_url_for_image
from app.services.search import normalize_tag_token, parse_media_type_filter, parse_rating_filter
from app.services.deletion import hard_delete_image
from app.services.rating_rules import load_rating_rule_map, reclassify_image_from_rules, resolve_open_reports_for_release
from app.services.tags import prune_orphan_tags
from app.services.visibility import (
    apply_public_image_visibility,
    image_has_blacklisted_tags,
    is_owner,
    is_staff,
    resolve_visibility_status,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import selectinload


router = APIRouter(prefix="/images")


def apply_visibility(query, current_user: User | None):
    return apply_public_image_visibility(query, current_user)


def apply_media_type_filter(query, db: DbSession, media_type: str | None):
    normalized = parse_media_type_filter(media_type)
    if not normalized:
        return query
    tag = db.query(Tag).filter(Tag.name_normalized == normalized).first()
    if not tag:
        return query.filter(False)
    return query.filter(Image.tags.any(and_(ImageTag.tag_id == tag.id)))


def attach_image_state(item: ImageListItem | ImageDetail, image: Image, current_user: User | None) -> None:
    item.visibility_status = resolve_visibility_status(image)
    if isinstance(item, ImageDetail):
        item.can_edit = bool(current_user and (is_staff(current_user) or is_owner(current_user, image)))
        item.can_delete = item.can_edit
        item.can_moderate = bool(current_user and is_staff(current_user))
        item.manual_tag_names = sorted(
            {
                image_tag.tag.name_normalized
                for image_tag in image.tags
                if image_tag.source == TagSource.USER
            }
        )


def ensure_access_to_image(image: Image, current_user: User | None) -> None:
    visibility_status = resolve_visibility_status(image)
    if visibility_status != VisibilityStatus.VISIBLE and not (
        current_user and (is_staff(current_user) or is_owner(current_user, image))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if image.rating == Rating.SENSITIVE and current_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if image.rating == Rating.QUESTIONABLE and not (
        current_user and (current_user.can_view_questionable or is_staff(current_user))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if image.rating == Rating.EXPLICIT and not (
        current_user and (current_user.can_view_explicit or is_staff(current_user))
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Explicit content requires opt-in")
    if image_has_blacklisted_tags(image, current_user) and not (
        current_user and (is_staff(current_user) or is_owner(current_user, image))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")


def ensure_image_for_write(image_id: str, db: DbSession) -> Image:
    image = (
        db.query(Image)
        .options(
            selectinload(Image.tags).selectinload(ImageTag.tag),
            selectinload(Image.moderation),
            selectinload(Image.uploaded_by),
        )
        .filter(Image.id == image_id)
        .first()
    )
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


def get_or_create_tag(db: DbSession, tag_name: str) -> Tag:
    normalized = normalize_tag_token(tag_name)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tag names must not be empty")
    tag = db.query(Tag).filter(Tag.name_normalized == normalized).first()
    if tag:
        return tag
    tag = Tag(name_normalized=normalized, display_name=normalized, category=TagCategory.GENERAL)
    db.add(tag)
    db.flush()
    return tag


def normalize_tag_names(raw_names: list[str]) -> list[str]:
    deduped_names: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_names:
        normalized = normalize_tag_token(raw_name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped_names.append(normalized)
    return deduped_names


@router.get("", response_model=ImageListResponse)
def list_images(
    db: DbSession,
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    rating: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
) -> ImageListResponse:
    query = (
        db.query(Image)
        .options(selectinload(Image.variants), selectinload(Image.uploaded_by))
        .filter(Image.processing_status == ProcessingStatus.READY)
    )
    parsed_rating = parse_rating_filter(rating)
    if parsed_rating is not None:
        query = query.filter(Image.rating == parsed_rating)
    query = apply_media_type_filter(query, db, media_type)
    query = apply_visibility(query, current_user)
    total_count = query.order_by(None).count()
    total_pages = max((total_count + limit - 1) // limit, 1)
    offset = (page - 1) * limit
    images = query.order_by(desc(Image.created_at)).offset(offset).limit(limit).all()
    items = []
    for image in images:
        item = ImageListItem.model_validate(image)
        item.thumb_url = thumb_url_for_image(image)
        attach_image_state(item, image, current_user)
        items.append(item)
    return ImageListResponse(
        data=items,
        meta={
            "count": len(images),
            "limit": limit,
            "page": page,
            "total_count": total_count,
            "total_pages": total_pages,
        },
        next_cursor=None,
    )


@router.get("/{image_id}", response_model=ImageDetailResponse)
def get_image(
    image_id: str,
    db: DbSession,
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> ImageDetailResponse:
    image = (
        db.query(Image)
        .options(
            selectinload(Image.variants),
            selectinload(Image.tags).selectinload(ImageTag.tag),
            selectinload(Image.uploaded_by),
            selectinload(Image.moderation),
        )
        .filter(Image.id == image_id)
        .first()
    )
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    ensure_access_to_image(image, current_user)
    detail = ImageDetail.model_validate(image)
    for variant in detail.variants:
        variant.url = build_media_url(variant.relative_path)
    attach_image_state(detail, image, current_user)
    return ImageDetailResponse(data=detail, meta={})


@router.get("/{image_id}/related")
def related_images(
    image_id: str,
    db: DbSession,
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
    limit: int = Query(default=12, ge=1, le=50),
) -> dict:
    image = db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    source_tag_ids = [item.tag_id for item in image.tags]
    if not source_tag_ids:
        return {"data": [], "meta": {"count": 0, "basis": "shared_tags"}}

    query = (
        db.query(Image, func.count(ImageTag.tag_id).label("shared_tag_count"))
        .join(ImageTag, ImageTag.image_id == Image.id)
        .filter(Image.id != image_id)
        .filter(ImageTag.tag_id.in_(source_tag_ids))
        .filter(Image.processing_status == ProcessingStatus.READY)
        .group_by(Image.id)
        .order_by(func.count(ImageTag.tag_id).desc(), Image.created_at.desc())
    )
    query = apply_visibility(query, current_user)

    rows = query.limit(limit).all()
    return {
        "data": [
            {
                "id": related.id,
                "uuid_short": related.uuid_short,
                "rating": related.rating.value,
                "shared_tag_count": shared_tag_count,
            }
            for related, shared_tag_count in rows
        ],
        "meta": {"count": len(rows), "basis": "shared_tags"},
    }


@router.post("/{image_id}/report")
def report_image(
    image_id: str,
    payload: ImageReportCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    image = ensure_image_for_write(image_id, db)
    report = ImageReport(
        image_id=image.id,
        reported_by_user_id=current_user.id,
        reason=payload.reason,
        message=payload.message.strip() if payload.message else None,
    )
    moderation = image.moderation or ImageModeration(image_id=image.id)
    if image.moderation is None or moderation.visibility_status in {None, VisibilityStatus.VISIBLE}:
        moderation.visibility_status = VisibilityStatus.HIDDEN
        moderation.reason = "reported"
        moderation.note = None
        moderation.acted_by_user_id = current_user.id
        moderation.acted_at = datetime.now(timezone.utc)
    db.add(moderation)
    db.add(report)
    db.commit()
    return {"data": {"status": "reported"}, "meta": {}}


@router.patch("/{image_id}/metadata")
def update_image_metadata(
    image_id: str,
    payload: ImageMetadataUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    image = ensure_image_for_write(image_id, db)
    staff = is_staff(current_user)
    owner = is_owner(current_user, image)
    tags_changed = False
    if not (staff or owner):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if payload.rating is not None:
        if not staff:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only moderators can change ratings")
        image.rating = payload.rating

    if payload.tag_names is not None:
        tags_changed = True
        affected_tag_ids = {image_tag.tag_id for image_tag in image.tags if image_tag.source == TagSource.USER}
        manual_tags = [item for item in image.tags if item.source == TagSource.USER]
        for image_tag in manual_tags:
            db.delete(image_tag)
        db.flush()
        deduped_names = normalize_tag_names(payload.tag_names)
        for tag_name in deduped_names:
            tag = get_or_create_tag(db, tag_name)
            affected_tag_ids.add(tag.id)
            db.add(
                ImageTag(
                    image_id=image.id,
                    tag_id=tag.id,
                    source=TagSource.USER,
                    confidence=None,
                    is_manual=True,
                )
            )
        db.flush()
        prune_orphan_tags(db, affected_tag_ids)

    if payload.remove_tag_names is not None:
        tags_changed = True
        removable_names = set(normalize_tag_names(payload.remove_tag_names))
        if removable_names:
            removed_tag_ids = {
                image_tag.tag_id
                for image_tag in image.tags
                if image_tag.tag.name_normalized in removable_names
            }
            for image_tag in list(image.tags):
                if image_tag.tag.name_normalized not in removable_names:
                    continue
                if owner and not staff and image_tag.source != TagSource.USER:
                    continue
                db.delete(image_tag)
            db.flush()
            prune_orphan_tags(db, removed_tag_ids)

    if payload.add_tag_names is not None:
        tags_changed = True
        existing_names = {image_tag.tag.name_normalized for image_tag in image.tags}
        add_names = normalize_tag_names(payload.add_tag_names)
        for tag_name in add_names:
            if tag_name in existing_names:
                continue
            tag = get_or_create_tag(db, tag_name)
            db.add(
                ImageTag(
                    image_id=image.id,
                    tag_id=tag.id,
                    source=TagSource.USER,
                    confidence=None,
                    is_manual=True,
                )
            )
            existing_names.add(tag_name)
        db.flush()

    if tags_changed and payload.rating is None:
        rule_map = load_rating_rule_map(db)
        if rule_map:
            refreshed_image = (
                db.query(Image)
                .options(selectinload(Image.tags).selectinload(ImageTag.tag))
                .filter(Image.id == image.id)
                .first()
            )
            if refreshed_image is not None:
                reclassify_image_from_rules(db, refreshed_image, rule_map)

    db.commit()
    return {"data": {"status": "updated"}, "meta": {}}


@router.patch("/{image_id}/visibility")
def update_image_visibility(
    image_id: str,
    payload: ImageVisibilityUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if not is_staff(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    image = ensure_image_for_write(image_id, db)
    moderation = image.moderation or ImageModeration(image_id=image.id)
    if image.moderation is None:
        image.moderation = moderation
    moderation.visibility_status = payload.visibility_status
    moderation.reason = payload.reason.strip() if payload.reason else None
    moderation.note = payload.note.strip() if payload.note else None
    moderation.acted_by_user_id = current_user.id
    moderation.acted_at = datetime.now(timezone.utc)
    if payload.visibility_status == VisibilityStatus.VISIBLE:
        resolve_open_reports_for_release(db, image, current_user, payload.note)
    db.add(moderation)
    db.commit()
    return {"data": {"status": payload.visibility_status.value}, "meta": {}}


@router.post("/{image_id}/delete")
def delete_image(
    image_id: str,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    image = ensure_image_for_write(image_id, db)
    if not (is_staff(current_user) or is_owner(current_user, image)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    hard_delete_image(db, image)
    db.commit()
    return {"data": {"status": "deleted"}, "meta": {}}
