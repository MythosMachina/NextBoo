from typing import Annotated

from app.api.deps import DbSession, require_roles
from app.api.deps import RedisClient
from app.core.constants import UserRole
from app.models.user import User
from app.schemas.app_settings import (
    RetagAllResponse,
    SidebarSettingsRead,
    SidebarSettingsResponse,
    SidebarSettingsUpdate,
    TaggerSettingsRead,
    TaggerSettingsResponse,
)
from app.services.app_settings import (
    RETAG_ALL_ACTION,
    get_tagger_provider,
    get_sidebar_limits,
    maintenance_pending_key,
    maintenance_queue_name_for_provider,
    maintenance_running_key,
    update_sidebar_limits,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text


class QueueMaintenancePayload(BaseModel):
    action: str
    requested_by_user_id: int
    requested_by_username: str


router = APIRouter(prefix="/admin/settings")


def build_tagger_settings_response(db: DbSession, redis: RedisClient) -> TaggerSettingsResponse:
    active_provider = get_tagger_provider(db)
    return TaggerSettingsResponse(
        data=TaggerSettingsRead(
            provider=active_provider,
            retag_all_running=bool(redis.exists(maintenance_running_key(active_provider, RETAG_ALL_ACTION))),
            retag_all_pending=bool(redis.exists(maintenance_pending_key(active_provider, RETAG_ALL_ACTION))),
        ),
        meta={},
    )


@router.get("/sidebar", response_model=SidebarSettingsResponse)
def get_sidebar_settings(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> SidebarSettingsResponse:
    return SidebarSettingsResponse(data=SidebarSettingsRead(**get_sidebar_limits(db)), meta={})


@router.patch("/sidebar", response_model=SidebarSettingsResponse)
def patch_sidebar_settings(
    payload: SidebarSettingsUpdate,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> SidebarSettingsResponse:
    sanitized = {
        key: max(getattr(payload, key), 0)
        for key in SidebarSettingsRead.model_fields.keys()
    }
    return SidebarSettingsResponse(data=SidebarSettingsRead(**update_sidebar_limits(db, sanitized)), meta={})


@router.get("/tagger", response_model=TaggerSettingsResponse)
def get_tagger_settings(
    db: DbSession,
    redis: RedisClient,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TaggerSettingsResponse:
    return build_tagger_settings_response(db, redis)


@router.post("/tagger/prune-retag", response_model=RetagAllResponse)
def enqueue_prune_and_retag(
    db: DbSession,
    redis: RedisClient,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> RetagAllResponse:
    active_provider = get_tagger_provider(db)
    pending_key = maintenance_pending_key(active_provider, RETAG_ALL_ACTION)
    running_key = maintenance_running_key(active_provider, RETAG_ALL_ACTION)

    if redis.exists(running_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A prune-and-retag task is already running for the active tagger.",
        )
    if not redis.set(pending_key, "1", nx=True, ex=3600):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A prune-and-retag task is already queued for the active tagger.",
        )

    queue_name = maintenance_queue_name_for_provider(active_provider)
    payload = QueueMaintenancePayload(
        action=RETAG_ALL_ACTION,
        requested_by_user_id=current_user.id,
        requested_by_username=current_user.username,
    )
    redis.rpush(queue_name, payload.model_dump_json())

    db.execute(text("UPDATE app_settings SET updated_at = NOW() WHERE key = :key"), {"key": "tagger_provider"})
    db.commit()
    response = build_tagger_settings_response(db, redis)
    return RetagAllResponse(data=response.data, meta={})
