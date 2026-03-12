from typing import Annotated

from app.api.deps import DbSession, get_optional_current_user
from app.core.constants import ProcessingStatus
from app.models.image import Image, ImageTag
from app.models.tag import Tag, TagAlias
from app.models.user import User
from app.services.search import normalize_tag_token, parse_media_type_filter, parse_rating_filter, parse_search_query
from app.services.visibility import apply_public_image_visibility
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc
from sqlalchemy.orm import selectinload
from app.services.media import thumb_url_for_image
from app.schemas.image import ImageListItem, ImageListResponse

router = APIRouter(prefix="/search")


def apply_media_type_filter(query, db: DbSession, media_type: str | None):
    normalized = parse_media_type_filter(media_type)
    if not normalized:
        return query
    tag = db.query(Tag).filter(Tag.name_normalized == normalized).first()
    if not tag:
        return query.filter(False)
    return query.filter(Image.tags.any(and_(ImageTag.tag_id == tag.id)))


@router.get("", response_model=ImageListResponse)
def search_images(
    db: DbSession,
    q: str = Query(default=""),
    rating: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> ImageListResponse:
    parsed = parse_search_query(q)
    query = (
        db.query(Image)
        .options(selectinload(Image.variants))
        .filter(Image.processing_status == ProcessingStatus.READY)
    )

    effective_rating = parse_rating_filter(rating) or parsed.rating
    if effective_rating:
        query = query.filter(Image.rating == effective_rating)

    query = apply_media_type_filter(query, db, media_type)

    query = apply_public_image_visibility(query, current_user)

    resolved_include = []
    for token in parsed.include_tags:
        alias = db.query(TagAlias).filter(TagAlias.alias_name == normalize_tag_token(token)).first()
        if alias:
            resolved_include.append(alias.target_tag_id)
            continue
        tag = db.query(Tag).filter(Tag.name_normalized == normalize_tag_token(token)).first()
        if tag:
            resolved_include.append(tag.id)

    for tag_id in resolved_include:
        query = query.filter(Image.tags.any(and_(ImageTag.tag_id == tag_id)))

    excluded_ids = []
    for token in parsed.exclude_tags:
        alias = db.query(TagAlias).filter(TagAlias.alias_name == normalize_tag_token(token)).first()
        if alias:
            excluded_ids.append(alias.target_tag_id)
            continue
        tag = db.query(Tag).filter(Tag.name_normalized == normalize_tag_token(token)).first()
        if tag:
            excluded_ids.append(tag.id)

    for tag_id in excluded_ids:
        query = query.filter(~Image.tags.any(and_(ImageTag.tag_id == tag_id)))

    order_clause = Image.created_at.asc() if parsed.sort == "oldest" else desc(Image.created_at)
    total_count = query.order_by(None).count()
    total_pages = max((total_count + limit - 1) // limit, 1)
    offset = (page - 1) * limit
    images = query.order_by(order_clause).offset(offset).limit(limit).all()
    items = []
    for image in images:
        item = ImageListItem.model_validate(image)
        item.thumb_url = thumb_url_for_image(image)
        items.append(item)
    return ImageListResponse(
        data=items,
        meta={
            "count": len(images),
            "query": q,
            "rating": effective_rating.value if effective_rating else None,
            "media_type": parse_media_type_filter(media_type),
            "sort": parsed.sort,
            "page": page,
            "limit": limit,
            "total_count": total_count,
            "total_pages": total_pages,
        },
        next_cursor=None,
    )
