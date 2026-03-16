import json
import logging
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Annotated

from app.api.deps import DbSession, RedisClient, get_current_user, get_optional_current_user, require_roles
from app.core.constants import ProcessingStatus, SYSTEM_TAGS, TagCategory, UserRole
from app.db.session import get_redis_client
from app.db.session import engine as db_engine
from app.models.image import Image, ImageTag
from app.models.tag import DangerTag, Tag, TagAlias, TagMerge
from app.models.user import User
from app.schemas.tag_admin import DangerTagEnvelope, DangerTagRead, DangerTagUpsert, TagAdminEnvelope, TagAdminRead, TagAliasUpsert, TagMergePayload, TagUpdatePayload
from app.services.app_settings import get_sidebar_limits
from app.services.tag_governance import is_name_pattern_tag
from app.services.rate_limits import enforce_rate_limit
from app.services.search import normalize_tag_token, parse_media_type_filter, parse_rating_filter, parse_search_query
from app.services.visibility import apply_public_image_visibility
from fastapi import APIRouter, Depends, Query, Request
from redis.exceptions import RedisError
from sqlalchemy import and_, desc, func, not_, or_
from sqlalchemy.orm import Session


router = APIRouter(prefix="/tags")


def get_or_create_tag(db: DbSession, tag_name: str) -> Tag:
    normalized = normalize_tag_token(tag_name)
    if not normalized:
        raise ValueError("Tag must not be empty")
    existing = db.query(Tag).filter(Tag.name_normalized == normalized).first()
    if existing:
        return existing
    tag = Tag(name_normalized=normalized, display_name=normalized, category=TagCategory.GENERAL)
    db.add(tag)
    db.flush()
    return tag

DEFAULT_BROWSER_OPEN_NAMESPACES = {"character", "general"}
CACHE_REGISTRY_KEY = "nextboo:tags:sidebar:registry"
CACHE_META_PREFIX = "nextboo:tags:sidebar:meta:"
CACHE_DATA_PREFIX = "nextboo:tags:sidebar:data:"
CACHE_TTL_SECONDS = 3600
CACHE_REFRESH_INTERVAL_SECONDS = 900
logger = logging.getLogger(__name__)


def build_filtered_images_subquery(
    db: DbSession,
    current_user: User | None,
    view_query: str,
    rating: str | None = None,
    media_type: str | None = None,
):
    parsed = parse_search_query(view_query)
    image_query = db.query(Image.id).filter(Image.processing_status == ProcessingStatus.READY)
    effective_rating = parse_rating_filter(rating) or parsed.rating
    if effective_rating:
        image_query = image_query.filter(Image.rating == effective_rating)
    image_query = apply_public_image_visibility(image_query, current_user)
    normalized_media_type = parse_media_type_filter(media_type)
    if normalized_media_type:
        media_tag = db.query(Tag).filter(Tag.name_normalized == normalized_media_type).first()
        if media_tag:
            image_query = image_query.filter(Image.tags.any(and_(ImageTag.tag_id == media_tag.id)))
        else:
            image_query = image_query.filter(False)

    resolved_include: list[int] = []
    for token in parsed.include_tags:
        alias = db.query(TagAlias).filter(TagAlias.alias_name == normalize_tag_token(token)).first()
        if alias:
            resolved_include.append(alias.target_tag_id)
            continue
        tag = db.query(Tag).filter(Tag.name_normalized == normalize_tag_token(token)).first()
        if tag:
            resolved_include.append(tag.id)

    excluded_ids: list[int] = []
    for token in parsed.exclude_tags:
        alias = db.query(TagAlias).filter(TagAlias.alias_name == normalize_tag_token(token)).first()
        if alias:
            excluded_ids.append(alias.target_tag_id)
            continue
        tag = db.query(Tag).filter(Tag.name_normalized == normalize_tag_token(token)).first()
        if tag:
            excluded_ids.append(tag.id)

    for tag_id in resolved_include:
        image_query = image_query.filter(Image.tags.any(and_(ImageTag.tag_id == tag_id)))
    for tag_id in excluded_ids:
        image_query = image_query.filter(~Image.tags.any(and_(ImageTag.tag_id == tag_id)))

    if parsed.sort == "oldest":
        image_query = image_query.order_by(Image.created_at.asc())
    else:
        image_query = image_query.order_by(desc(Image.created_at))

    return image_query.subquery()


def tag_usage_query(
    db: DbSession,
    current_user: User | None,
    view_query: str,
    rating: str | None = None,
    media_type: str | None = None,
):
    filtered_images = build_filtered_images_subquery(
        db,
        current_user,
        view_query,
        rating=rating,
        media_type=media_type,
    )
    query = (
        db.query(Tag, func.count(func.distinct(filtered_images.c.id)).label("usage_count"))
        .outerjoin(ImageTag, ImageTag.tag_id == Tag.id)
        .outerjoin(filtered_images, filtered_images.c.id == ImageTag.image_id)
        .filter(Tag.is_active.is_(True))
    )
    return query, filtered_images


def filter_tag_namespace(query, namespace: str):
    if namespace == "special":
        return query.filter(Tag.name_normalized.in_(SYSTEM_TAGS))
    if namespace == "meta":
        return query.filter(Tag.category == TagCategory.META).filter(not_(Tag.name_normalized.in_(SYSTEM_TAGS)))
    if namespace == "creature":
        return query.filter(Tag.name_normalized.like("%_(creature)"))
    if namespace == "artist":
        return query.filter(or_(Tag.category == TagCategory.ARTIST, Tag.name_normalized.like("%_(artist)")))
    if namespace == "series":
        return query.filter(
            or_(
                Tag.category == TagCategory.COPYRIGHT,
                Tag.name_normalized.like("%_(series)"),
                Tag.name_normalized.like("%_(copyright)"),
            )
        )
    if namespace == "character":
        return query.filter(Tag.category == TagCategory.CHARACTER)
    return query.filter(Tag.category == TagCategory.GENERAL)


def order_tag_usage(query):
    return query.group_by(Tag.id).order_by(func.count(ImageTag.image_id).desc(), Tag.name_normalized.asc())


def serialize_tag_rows(rows) -> list[dict]:
    return [
        {
            "id": tag.id,
            "name_normalized": tag.name_normalized,
            "display_name": tag.display_name,
            "category": tag.category.value,
            "usage_count": usage_count,
        }
        for tag, usage_count in rows
    ]


def build_browser_section_payload(query, limit: int, load_items: bool) -> dict:
    scoped_query = order_tag_usage(query)
    total_count = scoped_query.count()
    total_pages = max((total_count + limit - 1) // limit, 1)
    rows = scoped_query.limit(limit).all() if load_items else []
    return {
        "items": serialize_tag_rows(rows),
        "count": total_count,
        "page": 1,
        "total_pages": total_pages,
    }


def build_viewer_cache_scope(current_user: User | None) -> dict:
    if current_user is None:
        return {
            "role": "guest",
            "can_view_questionable": False,
            "can_view_explicit": False,
            "tag_blacklist": "",
        }
    return {
        "role": current_user.role.value,
        "can_view_questionable": bool(current_user.can_view_questionable),
        "can_view_explicit": bool(current_user.can_view_explicit),
        "tag_blacklist": current_user.tag_blacklist or "",
    }


def rehydrate_viewer_cache_scope(scope: dict) -> User | None:
    if scope.get("role") == "guest":
        return None
    return SimpleNamespace(
        role=scope.get("role"),
        can_view_questionable=bool(scope.get("can_view_questionable")),
        can_view_explicit=bool(scope.get("can_view_explicit")),
        tag_blacklist=scope.get("tag_blacklist", ""),
    )


def build_sidebar_cache_key(q: str, rating: str | None, media_type: str | None, current_user: User | None) -> str:
    scope = build_viewer_cache_scope(current_user)
    normalized = json.dumps(
        {
            "q": q,
            "rating": parse_rating_filter(rating).value if parse_rating_filter(rating) else None,
            "media_type": parse_media_type_filter(media_type),
            "scope": scope,
        },
        sort_keys=True,
    )
    return normalized


def build_sidebar_payload(
    db: DbSession,
    q: str,
    rating: str | None,
    media_type: str | None,
    current_user: User | None,
) -> dict:
    limits = get_sidebar_limits(db)
    base_query, filtered_images = tag_usage_query(db, current_user, q, rating=rating, media_type=media_type)

    special_rows = (
        filter_tag_namespace(base_query, "special")
        .group_by(Tag.id)
        .order_by(Tag.name_normalized.asc())
        .all()
    )

    meta_rows = (
        order_tag_usage(filter_tag_namespace(base_query, "meta").filter(filtered_images.c.id.is_not(None)))
        .limit(limits["sidebar_meta_limit"])
        .all()
    )

    creature_rows = (
        order_tag_usage(filter_tag_namespace(base_query, "creature").filter(filtered_images.c.id.is_not(None)))
        .limit(limits["sidebar_creature_limit"])
        .all()
    )
    creature_ids = {tag.id for tag, _ in creature_rows}

    artist_rows = (
        order_tag_usage(filter_tag_namespace(base_query, "artist").filter(filtered_images.c.id.is_not(None)))
        .limit(limits["sidebar_artist_limit"])
        .all()
    )
    artist_ids = {tag.id for tag, _ in artist_rows}

    series_rows = (
        order_tag_usage(filter_tag_namespace(base_query, "series").filter(filtered_images.c.id.is_not(None)))
        .limit(limits["sidebar_series_limit"])
        .all()
    )
    series_ids = {tag.id for tag, _ in series_rows}

    character_rows = filter_tag_namespace(base_query, "character").filter(filtered_images.c.id.is_not(None))
    if creature_ids or artist_ids or series_ids:
        character_rows = character_rows.filter(not_(Tag.id.in_(tuple(creature_ids | artist_ids | series_ids))))
    character_rows = (
        order_tag_usage(character_rows)
        .limit(limits["sidebar_character_limit"])
        .all()
    )
    promoted_ids = {tag.id for tag, _ in meta_rows + creature_rows + artist_rows + series_rows + character_rows}

    general_query = filter_tag_namespace(base_query, "general").filter(filtered_images.c.id.is_not(None))
    if promoted_ids:
        general_query = general_query.filter(not_(Tag.id.in_(tuple(promoted_ids))))
    general_rows = (
        order_tag_usage(general_query)
        .limit(limits["sidebar_general_limit"])
        .all()
    )
    browser_payload = {
        "character": build_browser_section_payload(
            filter_tag_namespace(base_query, "character").filter(filtered_images.c.id.is_not(None)),
            limits["sidebar_character_limit"],
            load_items="character" in DEFAULT_BROWSER_OPEN_NAMESPACES,
        ),
        "artist": build_browser_section_payload(
            filter_tag_namespace(base_query, "artist").filter(filtered_images.c.id.is_not(None)),
            limits["sidebar_artist_limit"],
            load_items="artist" in DEFAULT_BROWSER_OPEN_NAMESPACES,
        ),
        "series": build_browser_section_payload(
            filter_tag_namespace(base_query, "series").filter(filtered_images.c.id.is_not(None)),
            limits["sidebar_series_limit"],
            load_items="series" in DEFAULT_BROWSER_OPEN_NAMESPACES,
        ),
        "creature": build_browser_section_payload(
            filter_tag_namespace(base_query, "creature").filter(filtered_images.c.id.is_not(None)),
            limits["sidebar_creature_limit"],
            load_items="creature" in DEFAULT_BROWSER_OPEN_NAMESPACES,
        ),
        "meta": build_browser_section_payload(
            filter_tag_namespace(base_query, "meta").filter(filtered_images.c.id.is_not(None)),
            limits["sidebar_meta_limit"],
            load_items="meta" in DEFAULT_BROWSER_OPEN_NAMESPACES,
        ),
        "general": build_browser_section_payload(
            filter_tag_namespace(base_query, "general").filter(filtered_images.c.id.is_not(None)),
            limits["sidebar_general_limit"],
            load_items="general" in DEFAULT_BROWSER_OPEN_NAMESPACES,
        ),
    }
    browser_counts = {namespace: payload["count"] for namespace, payload in browser_payload.items()}

    return {
        "data": {
            "special": serialize_tag_rows(special_rows),
            "promoted_meta": serialize_tag_rows(meta_rows),
            "character": serialize_tag_rows(character_rows),
            "artist": serialize_tag_rows(artist_rows),
            "series": serialize_tag_rows(series_rows),
            "creature": serialize_tag_rows(creature_rows),
            "general": serialize_tag_rows(general_rows),
            "limits": limits,
            "counts": browser_counts,
            "browser": browser_payload,
        },
        "meta": {},
    }


def store_sidebar_cache(redis_client, cache_key: str, source_payload: dict, response_payload: dict) -> None:
    try:
        redis_client.set(f"{CACHE_DATA_PREFIX}{cache_key}", json.dumps(response_payload), ex=CACHE_TTL_SECONDS)
        redis_client.set(f"{CACHE_META_PREFIX}{cache_key}", json.dumps(source_payload), ex=CACHE_TTL_SECONDS)
        redis_client.sadd(CACHE_REGISTRY_KEY, cache_key)
    except RedisError:
        logger.exception("failed to store sidebar cache")


def refresh_sidebar_cache_registry(stop_event: threading.Event) -> None:
    while not stop_event.wait(CACHE_REFRESH_INTERVAL_SECONDS):
        try:
            redis_client = get_redis_client()
            cache_keys = redis_client.smembers(CACHE_REGISTRY_KEY)
        except RedisError:
            logger.exception("failed to load sidebar cache registry")
            continue
        for cache_key in cache_keys:
            try:
                raw_meta = redis_client.get(f"{CACHE_META_PREFIX}{cache_key}")
                if not raw_meta:
                    continue
                meta = json.loads(raw_meta)
                with Session(db_engine) as session:
                    viewer = rehydrate_viewer_cache_scope(meta.get("scope", {}))
                    payload = build_sidebar_payload(
                        session,
                        meta.get("q", ""),
                        meta.get("rating"),
                        meta.get("media_type"),
                        viewer,
                    )
                    store_sidebar_cache(redis_client, cache_key, meta, payload)
            except Exception:
                logger.exception("failed to refresh sidebar cache key")


@router.get("/sidebar")
def sidebar_tags(
    db: DbSession,
    redis_client: RedisClient,
    q: str = Query(default=""),
    rating: str | None = Query(default=None),
    media_type: str | None = Query(default=None),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> dict:
    cache_key = build_sidebar_cache_key(q, rating, media_type, current_user)
    try:
        cached = redis_client.get(f"{CACHE_DATA_PREFIX}{cache_key}")
        if cached:
            return json.loads(cached)
    except RedisError:
        logger.exception("failed to load sidebar cache")

    source_payload = {
        "q": q,
        "rating": parse_rating_filter(rating).value if parse_rating_filter(rating) else None,
        "media_type": parse_media_type_filter(media_type),
        "scope": build_viewer_cache_scope(current_user),
    }
    payload = build_sidebar_payload(db, q, rating, media_type, current_user)
    store_sidebar_cache(redis_client, cache_key, source_payload, payload)
    return payload


@router.get("/browser")
def browser_tags(
    db: DbSession,
    namespace: str = Query(default="general", pattern="^(general|character|artist|series|creature|meta)$"),
    q: str = Query(default=""),
    view_q: str = Query(default=""),
    view_rating: str | None = Query(default=None),
    view_media_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> dict:
    base_query, filtered_images = tag_usage_query(
        db,
        current_user,
        view_q,
        rating=view_rating,
        media_type=view_media_type,
    )
    base_query = filter_tag_namespace(base_query, namespace).filter(filtered_images.c.id.is_not(None))
    if q:
        base_query = base_query.filter(Tag.name_normalized.ilike(f"%{q.lower()}%"))
    total_count = order_tag_usage(base_query).count()
    total_pages = max((total_count + limit - 1) // limit, 1)
    rows = order_tag_usage(base_query).offset((page - 1) * limit).limit(limit).all()
    return {
        "data": serialize_tag_rows(rows),
        "meta": {
            "namespace": namespace,
            "count": len(rows),
            "total_count": total_count,
            "page": page,
            "total_pages": total_pages,
            "query": q,
        },
    }


@router.get("/autocomplete")
def autocomplete_tags(
    db: DbSession,
    q: str = Query(default="", min_length=1),
    limit: int = Query(default=8, ge=1, le=25),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> dict:
    query = (
        db.query(Tag, func.count(func.distinct(Image.id)).label("usage_count"))
        .outerjoin(ImageTag, ImageTag.tag_id == Tag.id)
        .outerjoin(Image, and_(Image.id == ImageTag.image_id, Image.processing_status == ProcessingStatus.READY))
        .filter(Tag.is_active.is_(True))
        .filter(Tag.name_normalized.ilike(f"{q.lower()}%"))
    )
    query = apply_public_image_visibility(query, current_user)
    tags = (
        query.group_by(Tag.id)
        .order_by(func.count(ImageTag.image_id).desc(), Tag.name_normalized.asc())
        .limit(limit)
        .all()
    )
    return {
        "data": [
            {
                "id": tag.id,
                "name_normalized": tag.name_normalized,
                "display_name": tag.display_name,
                "category": tag.category.value,
                "usage_count": usage_count,
            }
            for tag, usage_count in tags
        ],
        "meta": {"count": len(tags), "query": q},
    }


@router.get("/admin/list", response_model=TagAdminEnvelope)
def admin_list_tags(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    q: str = Query(default=""),
    limit: int = Query(default=200, ge=1, le=500),
) -> TagAdminEnvelope:
    image_count = func.count(func.distinct(ImageTag.image_id))
    alias_count = func.count(func.distinct(TagAlias.id))
    query = (
        db.query(Tag, image_count.label("image_count"), alias_count.label("alias_count"))
        .outerjoin(ImageTag, ImageTag.tag_id == Tag.id)
        .outerjoin(TagAlias, TagAlias.target_tag_id == Tag.id)
        .group_by(Tag.id)
    )
    if q.strip():
        normalized = normalize_tag_token(q)
        query = query.filter(or_(Tag.name_normalized.ilike(f"%{normalized}%"), Tag.display_name.ilike(f"%{q.strip()}%")))
    rows = query.order_by(image_count.desc(), Tag.name_normalized.asc()).limit(limit).all()
    return TagAdminEnvelope(
        data=[
            TagAdminRead(
                id=tag.id,
                name_normalized=tag.name_normalized,
                display_name=tag.display_name,
                category=tag.category,
                is_active=tag.is_active,
                is_locked=tag.is_locked,
                alias_count=int(alias_count_value or 0),
                image_count=int(image_count_value or 0),
                is_name_pattern=is_name_pattern_tag(tag),
            )
            for tag, image_count_value, alias_count_value in rows
        ],
        meta={"count": len(rows), "query": q},
    )


@router.patch("/admin/{tag_id}")
def admin_update_tag(
    tag_id: int,
    payload: TagUpdatePayload,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    tag = db.get(Tag, tag_id)
    if not tag:
        return {"data": {"status": "not_found"}, "meta": {"tag_id": tag_id}}
    if payload.display_name is not None:
        tag.display_name = payload.display_name.strip() or tag.display_name
    if payload.category is not None:
        tag.category = payload.category
    if payload.is_active is not None:
        tag.is_active = payload.is_active
    if payload.is_locked is not None:
        tag.is_locked = payload.is_locked
    db.add(tag)
    db.commit()
    return {"data": {"status": "updated", "tag_id": tag.id}, "meta": {}}


@router.post("/admin/alias")
def admin_upsert_alias(
    payload: TagAliasUpsert,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    target_tag = get_or_create_tag(db, payload.target_tag_name)
    alias_name = normalize_tag_token(payload.alias_name)
    alias = db.query(TagAlias).filter(TagAlias.alias_name == alias_name).first()
    if alias is None:
        alias = TagAlias(alias_name=alias_name, target_tag_id=target_tag.id, alias_type=payload.alias_type)
    else:
        alias.target_tag_id = target_tag.id
        alias.alias_type = payload.alias_type
    db.add(alias)
    db.commit()
    return {"data": {"status": "saved", "alias_name": alias_name, "target_tag": target_tag.name_normalized}, "meta": {}}


@router.post("/admin/merge")
def admin_merge_tags(
    payload: TagMergePayload,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if current_user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
        return {"data": {"status": "forbidden"}, "meta": {}}
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    source_tag = db.query(Tag).filter(Tag.name_normalized == normalize_tag_token(payload.source_tag_name)).first()
    target_tag = get_or_create_tag(db, payload.target_tag_name)
    if not source_tag:
        return {"data": {"status": "source_not_found"}, "meta": {}}
    if source_tag.id == target_tag.id:
        return {"data": {"status": "noop"}, "meta": {}}

    source_links = db.query(ImageTag).filter(ImageTag.tag_id == source_tag.id).all()
    for link in source_links:
        existing = (
            db.query(ImageTag)
            .filter(
                ImageTag.image_id == link.image_id,
                ImageTag.tag_id == target_tag.id,
                ImageTag.source == link.source,
            )
            .first()
        )
        if existing:
            if existing.confidence is None or (link.confidence is not None and link.confidence > existing.confidence):
                existing.confidence = link.confidence
                db.add(existing)
            db.delete(link)
        else:
            link.tag_id = target_tag.id
            db.add(link)

    for alias in db.query(TagAlias).filter(TagAlias.target_tag_id == source_tag.id).all():
        alias.target_tag_id = target_tag.id
        db.add(alias)
    if not db.query(TagAlias).filter(TagAlias.alias_name == source_tag.name_normalized).first():
        db.add(TagAlias(alias_name=source_tag.name_normalized, target_tag_id=target_tag.id))

    source_danger = db.query(DangerTag).filter(DangerTag.tag_id == source_tag.id).first()
    if source_danger:
        existing_danger = db.query(DangerTag).filter(DangerTag.tag_id == target_tag.id).first()
        if existing_danger:
            db.delete(source_danger)
        else:
            source_danger.tag_id = target_tag.id
            db.add(source_danger)

    db.add(
        TagMerge(
            source_tag_id=source_tag.id,
            target_tag_id=target_tag.id,
            merged_by_user_id=current_user.id,
            merged_at=datetime.now(timezone.utc),
            reason=payload.reason,
        )
    )
    db.delete(source_tag)
    db.commit()
    return {"data": {"status": "merged", "source_tag": payload.source_tag_name, "target_tag": target_tag.name_normalized}, "meta": {}}


@router.get("/admin/danger-tags", response_model=DangerTagEnvelope)
def list_danger_tags(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> DangerTagEnvelope:
    rows = db.query(DangerTag, Tag).join(Tag, Tag.id == DangerTag.tag_id).order_by(Tag.name_normalized.asc()).all()
    return DangerTagEnvelope(
        data=[
            DangerTagRead(
                id=rule.id,
                tag_id=tag.id,
                tag_name=tag.name_normalized,
                display_name=tag.display_name,
                reason=rule.reason,
                is_enabled=rule.is_enabled,
                created_at=rule.created_at,
            )
            for rule, tag in rows
        ],
        meta={"count": len(rows)},
    )


@router.put("/admin/danger-tags")
def upsert_danger_tag(
    payload: DangerTagUpsert,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if current_user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
        return {"data": {"status": "forbidden"}, "meta": {}}
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    tag = get_or_create_tag(db, payload.tag_name)
    rule = db.query(DangerTag).filter(DangerTag.tag_id == tag.id).first()
    if rule is None:
        rule = DangerTag(tag_id=tag.id, created_by_user_id=current_user.id)
    rule.reason = payload.reason.strip() if payload.reason else None
    rule.is_enabled = payload.is_enabled
    db.add(rule)
    db.commit()
    return {"data": {"status": "saved", "tag_name": tag.name_normalized}, "meta": {}}


@router.delete("/admin/danger-tags/{danger_tag_id}")
def delete_danger_tag(
    danger_tag_id: int,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    rule = db.get(DangerTag, danger_tag_id)
    if not rule:
        return {"data": {"status": "not_found"}, "meta": {"danger_tag_id": danger_tag_id}}
    db.delete(rule)
    db.commit()
    return {"data": {"status": "deleted"}, "meta": {}}


@router.get("")
def list_tags(
    db: DbSession,
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=1000),
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> dict:
    query = (
        db.query(Tag, func.count(func.distinct(Image.id)).label("usage_count"))
        .outerjoin(ImageTag, ImageTag.tag_id == Tag.id)
        .outerjoin(Image, and_(Image.id == ImageTag.image_id, Image.processing_status == ProcessingStatus.READY))
        .filter(Tag.is_active.is_(True))
    )
    query = apply_public_image_visibility(query, current_user)
    query = query.filter(or_(Image.id.is_(None), Image.processing_status == ProcessingStatus.READY))
    if q:
        query = query.filter(Tag.name_normalized.ilike(f"%{q.lower()}%"))
    tags = (
        query.group_by(Tag.id)
        .order_by(func.count(ImageTag.image_id).desc(), Tag.name_normalized.asc())
        .limit(limit)
        .all()
    )
    if not q:
        existing_names = {tag.name_normalized for tag, _ in tags}
        missing_system_tags = (
            query.filter(Tag.category == TagCategory.META, Tag.name_normalized.in_(SYSTEM_TAGS))
            .filter(~Tag.name_normalized.in_(existing_names))
            .group_by(Tag.id)
            .order_by(Tag.name_normalized.asc())
            .all()
        )
        tags.extend(missing_system_tags)
    return {
        "data": [
            {
                "id": tag.id,
                "name_normalized": tag.name_normalized,
                "display_name": tag.display_name,
                "category": tag.category.value,
                "usage_count": usage_count,
            }
            for tag, usage_count in tags
        ],
        "meta": {"count": len(tags), "query": q},
    }
