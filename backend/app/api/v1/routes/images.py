from datetime import datetime, timezone
from typing import Annotated

from app.api.deps import DbSession, get_current_user, get_optional_current_user
from app.core.constants import ProcessingStatus, Rating, TagCategory, TagSource, UserRole, VariantType, VisibilityStatus
from app.models.image import Image, ImageTag
from app.models.comment import CommentVote, ImageComment
from app.models.moderation import ImageModeration, ImageReport
from app.models.tag import Tag
from app.models.user import User
from app.models.vote import UserVoteThrottle
from app.schemas.image import ImageDetail, ImageDetailResponse, ImageListItem, ImageListResponse
from app.schemas.comment import CommentVoteCreate, ImageCommentCreate, ImageCommentRead, ImageCommentUpdate
from app.schemas.moderation import ImageMetadataUpdate, ImageReportCreate, ImageVisibilityUpdate
from app.schemas.vote import ImageVoteCreate, ImageVoteRead
from app.services.media import build_media_url, preview_url_for_image, thumb_url_for_image
from app.services.rating_cues import apply_staff_rating_cues
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
from app.services.votes import (
    current_cooldown_remaining,
    get_or_create_vote_throttle,
    get_user_vote,
    get_vote_score,
    get_vote_throttle,
    register_vote_action,
    upsert_image_vote,
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


def attach_vote_state(db: DbSession, item: ImageListItem | ImageDetail, image_id: str, current_user: User | None) -> None:
    item.vote_score = get_vote_score(db, image_id)
    if isinstance(item, ImageDetail):
        item.current_user_vote = get_user_vote(db, image_id, current_user.id if current_user else None)
        if current_user:
            throttle = get_vote_throttle(db, current_user.id)
            item.vote_cooldown_remaining_seconds = current_cooldown_remaining(throttle) if throttle else 0
        else:
            item.vote_cooldown_remaining_seconds = 0


def build_comment_tree(db: DbSession, comments: list[ImageComment], current_user: User | None) -> list[ImageCommentRead]:
    comment_scores = {
        comment_id: int(score or 0)
        for comment_id, score in (
            db.query(CommentVote.comment_id, func.coalesce(func.sum(CommentVote.value), 0))
            .filter(CommentVote.comment_id.in_([comment.id for comment in comments]))
            .group_by(CommentVote.comment_id)
            .all()
        )
    } if comments else {}
    current_user_votes = {}
    if current_user and comments:
        current_user_votes = {
            comment_id: int(value)
            for comment_id, value in (
                db.query(CommentVote.comment_id, CommentVote.value)
                .filter(CommentVote.user_id == current_user.id, CommentVote.comment_id.in_([comment.id for comment in comments]))
                .all()
            )
        }

    nodes: dict[int, ImageCommentRead] = {}
    roots: list[ImageCommentRead] = []
    ordered_comments = sorted(comments, key=lambda item: (item.parent_comment_id or 0, item.created_at))
    for comment in ordered_comments:
        if not comment.user or not comment.user.is_active:
            continue
        node = ImageCommentRead(
            id=comment.id,
            body=comment.body,
            is_edited=comment.is_edited,
            is_flagged=comment.is_flagged,
            score=comment_scores.get(comment.id, 0),
            current_user_vote=current_user_votes.get(comment.id),
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            author={"id": comment.user.id, "username": comment.user.username},
            replies=[],
        )
        nodes[comment.id] = node
        if comment.parent_comment_id and comment.parent_comment_id in nodes:
            nodes[comment.parent_comment_id].replies.append(node)
        else:
            roots.append(node)
    return roots


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
        item.preview_url = preview_url_for_image(image)
        preview_variant = next((variant for variant in image.variants if variant.variant_type == VariantType.PREVIEW), None)
        item.preview_mime_type = preview_variant.mime_type if preview_variant else None
        attach_image_state(item, image, current_user)
        attach_vote_state(db, item, image.id, current_user)
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
            selectinload(Image.comments).selectinload(ImageComment.user),
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
    detail.comments = build_comment_tree(db, image.comments, current_user)
    attach_image_state(detail, image, current_user)
    attach_vote_state(db, detail, image.id, current_user)
    apply_staff_rating_cues(detail, current_user)
    return ImageDetailResponse(data=detail, meta={})


@router.get("/{image_id}/related", response_model=ImageListResponse)
def related_images(
    image_id: str,
    db: DbSession,
    limit: int = Query(default=12, ge=1, le=50),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> ImageListResponse:
    image = (
        db.query(Image)
        .options(selectinload(Image.tags).selectinload(ImageTag.tag))
        .filter(Image.id == image_id)
        .first()
    )
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    ensure_access_to_image(image, current_user)
    relevant_tag_ids = [
        image_tag.tag_id
        for image_tag in image.tags
        if image_tag.tag.category in {TagCategory.GENERAL, TagCategory.CHARACTER, TagCategory.COPYRIGHT, TagCategory.ARTIST}
        and image_tag.tag.name_normalized not in {"image", "animated", "video"}
    ]
    if not relevant_tag_ids:
        return ImageListResponse(data=[], meta={"count": 0, "image_id": image_id}, next_cursor=None)

    shared_count = func.count(ImageTag.tag_id)
    query = (
        db.query(Image)
        .join(ImageTag, ImageTag.image_id == Image.id)
        .options(selectinload(Image.variants), selectinload(Image.uploaded_by))
        .filter(Image.id != image_id, Image.processing_status == ProcessingStatus.READY, ImageTag.tag_id.in_(relevant_tag_ids))
        .group_by(Image.id)
        .order_by(shared_count.desc(), desc(Image.created_at))
    )
    query = apply_visibility(query, current_user)
    images = query.limit(limit).all()
    items = []
    for related in images:
        item = ImageListItem.model_validate(related)
        item.thumb_url = thumb_url_for_image(related)
        item.preview_url = preview_url_for_image(related)
        preview_variant = next((variant for variant in related.variants if variant.variant_type == VariantType.PREVIEW), None)
        item.preview_mime_type = preview_variant.mime_type if preview_variant else None
        attach_image_state(item, related, current_user)
        attach_vote_state(db, item, related.id, current_user)
        items.append(item)
    return ImageListResponse(data=items, meta={"count": len(items), "image_id": image_id}, next_cursor=None)


@router.post("/{image_id}/vote")
def vote_on_image(
    image_id: str,
    payload: ImageVoteCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if payload.value not in {-1, 1}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Votes must be either +1 or -1.")

    image = db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    ensure_access_to_image(image, current_user)

    existing_vote = get_user_vote(db, image_id, current_user.id)
    if existing_vote == payload.value:
        throttle = get_or_create_vote_throttle(db, current_user.id)
        return {
            "data": ImageVoteRead(
                image_id=image_id,
                vote_score=get_vote_score(db, image_id),
                current_user_vote=existing_vote,
                vote_cooldown_remaining_seconds=current_cooldown_remaining(throttle),
            ).model_dump(),
            "meta": {"status": "unchanged"},
        }

    throttle = get_or_create_vote_throttle(db, current_user.id)
    remaining_seconds = current_cooldown_remaining(throttle)
    if remaining_seconds > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "Vote cooldown active.",
                "retry_after_seconds": remaining_seconds,
            },
        )

    upsert_image_vote(db, image_id, current_user.id, payload.value)
    cooldown_seconds = register_vote_action(db, current_user.id)
    db.commit()

    return {
        "data": ImageVoteRead(
            image_id=image_id,
            vote_score=get_vote_score(db, image_id),
            current_user_vote=get_user_vote(db, image_id, current_user.id),
            vote_cooldown_remaining_seconds=cooldown_seconds,
        ).model_dump(),
        "meta": {"status": "recorded"},
    }


@router.post("/{image_id}/comments")
def create_image_comment(
    image_id: str,
    payload: ImageCommentCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    image = db.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    ensure_access_to_image(image, current_user)
    parent_comment = None
    if payload.parent_comment_id is not None:
        parent_comment = db.get(ImageComment, payload.parent_comment_id)
        if not parent_comment or parent_comment.image_id != image.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")
        if parent_comment.parent_comment_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Replies can only target top-level comments.")

    now = datetime.now(timezone.utc)
    comment = ImageComment(
        image_id=image.id,
        user_id=current_user.id,
        parent_comment_id=parent_comment.id if parent_comment else None,
        body=payload.body.strip(),
        is_edited=False,
        is_flagged=False,
        moderation_reason=None,
        created_at=now,
        updated_at=now,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {
        "data": ImageCommentRead(
            id=comment.id,
            body=comment.body,
            is_edited=comment.is_edited,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            author={"id": current_user.id, "username": current_user.username},
            score=0,
            current_user_vote=None,
            is_flagged=False,
            replies=[],
        ).model_dump(),
        "meta": {"status": "created"},
    }


@router.post("/{image_id}/comments/{comment_id}/vote")
def vote_on_comment(
    image_id: str,
    comment_id: int,
    payload: CommentVoteCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if payload.value not in {-1, 1}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Votes must be either +1 or -1.")
    comment = db.get(ImageComment, comment_id)
    if not comment or comment.image_id != image_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    throttle = get_or_create_vote_throttle(db, current_user.id)
    remaining_seconds = current_cooldown_remaining(throttle)
    if remaining_seconds > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Vote cooldown active.", "retry_after_seconds": remaining_seconds},
        )

    existing_vote = db.get(CommentVote, {"comment_id": comment_id, "user_id": current_user.id})
    now = datetime.now(timezone.utc)
    if existing_vote is None:
        existing_vote = CommentVote(comment_id=comment_id, user_id=current_user.id, value=payload.value, created_at=now, updated_at=now)
        db.add(existing_vote)
    else:
        existing_vote.value = payload.value
        existing_vote.updated_at = now
        db.add(existing_vote)

    cooldown_seconds = register_vote_action(db, current_user.id)
    score = (
        db.query(func.coalesce(func.sum(CommentVote.value), 0))
        .filter(CommentVote.comment_id == comment_id)
        .scalar()
    )
    comment.is_flagged = int(score or 0) < 0
    db.add(comment)
    db.commit()
    refreshed_score = (
        db.query(func.coalesce(func.sum(CommentVote.value), 0))
        .filter(CommentVote.comment_id == comment_id)
        .scalar()
    )
    return {
        "data": {
            "comment_id": comment_id,
            "score": int(refreshed_score or 0),
            "current_user_vote": payload.value,
            "vote_cooldown_remaining_seconds": cooldown_seconds,
            "is_flagged": comment.is_flagged,
        },
        "meta": {"status": "recorded"},
    }


@router.patch("/{image_id}/comments/{comment_id}")
def update_comment(
    image_id: str,
    comment_id: int,
    payload: ImageCommentUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    comment = db.get(ImageComment, comment_id)
    if not comment or comment.image_id != image_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not is_staff(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    reason = (payload.moderation_reason or "").strip()
    if current_user.role == UserRole.MODERATOR and not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Moderation reason is required.")
    comment.body = payload.body.strip()
    if reason:
        comment.body = f"{comment.body}\n\nModeration change Reason: {reason}"
    comment.moderation_reason = reason or None
    comment.is_edited = True
    comment.updated_at = datetime.now(timezone.utc)
    db.add(comment)
    db.commit()
    return {"data": {"status": "updated"}, "meta": {}}


@router.delete("/{image_id}/comments/{comment_id}")
def delete_comment(
    image_id: str,
    comment_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    comment = db.get(ImageComment, comment_id)
    if not comment or comment.image_id != image_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not is_staff(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db.delete(comment)
    db.commit()
    return {"data": {"status": "deleted"}, "meta": {}}


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
