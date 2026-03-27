from typing import Annotated

from app.api.deps import DbSession, RedisClient, require_roles
from app.core.constants import UserRole
from app.models.user import User
from app.schemas.upload_pipeline import UploadPipelineControlRoomResponse
from app.services.upload_pipeline import (
    acknowledge_failed_final_ingest_jobs,
    acknowledge_failed_items,
    build_control_room_snapshot,
)
from app.services.rate_limits import enforce_rate_limit
from fastapi import APIRouter, Depends, Request


router = APIRouter(prefix="/admin/upload-pipeline")


@router.get("", response_model=UploadPipelineControlRoomResponse)
def get_upload_pipeline_control_room(
    db: DbSession,
    redis: RedisClient,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> UploadPipelineControlRoomResponse:
    return UploadPipelineControlRoomResponse(data=build_control_room_snapshot(db, redis), meta={})


@router.post("/acknowledge-failed", response_model=UploadPipelineControlRoomResponse)
def acknowledge_upload_pipeline_failed(
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> UploadPipelineControlRoomResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    removed = acknowledge_failed_items(db)
    return UploadPipelineControlRoomResponse(
        data=build_control_room_snapshot(db, redis),
        meta={"acknowledged_failed_items": removed},
    )


@router.post("/acknowledge-final-failed", response_model=UploadPipelineControlRoomResponse)
def acknowledge_upload_pipeline_final_failed(
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> UploadPipelineControlRoomResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    removed = acknowledge_failed_final_ingest_jobs(db)
    return UploadPipelineControlRoomResponse(
        data=build_control_room_snapshot(db, redis),
        meta={"acknowledged_final_failed_jobs": removed},
    )
