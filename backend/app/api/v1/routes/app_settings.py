import json

from typing import Annotated

from app.api.deps import DbSession, require_roles
from app.api.deps import RedisClient
from app.core.constants import UserRole
from app.models.user import User
from app.schemas.app_settings import (
    AutoscalerSettingsRead,
    AutoscalerSettingsResponse,
    AutoscalerSettingsUpdate,
    PreviewBackfillResponse,
    RateLimitSettingsRead,
    RateLimitSettingsResponse,
    RateLimitSettingsUpdate,
    RetagAllResponse,
    SidebarSettingsRead,
    SidebarSettingsResponse,
    SidebarSettingsUpdate,
    TaggerSettingsRead,
    TaggerSettingsResponse,
    UploadPipelineBalancerSettingsRead,
    UploadPipelineBalancerSettingsResponse,
    UploadPipelineBalancerSettingsUpdate,
    TermsOfServiceRead,
    TermsOfServiceResponse,
    TermsOfServiceUpdate,
)
from app.services.app_settings import (
    PREVIEW_BACKFILL_ACTION,
    RETAG_ALL_ACTION,
    get_autoscaler_settings,
    get_near_duplicate_threshold,
    get_rate_limit_settings,
    get_tagger_provider,
    get_terms_of_service,
    get_upload_pipeline_balancer_settings,
    get_sidebar_limits,
    maintenance_pending_key,
    maintenance_queue_name_for_provider,
    maintenance_running_key,
    update_autoscaler_settings,
    update_near_duplicate_threshold,
    update_rate_limit_settings,
    update_sidebar_limits,
    update_terms_of_service,
    update_upload_pipeline_balancer_settings,
)
from app.services.rate_limits import enforce_rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
            preview_backfill_running=bool(redis.exists(maintenance_running_key(active_provider, PREVIEW_BACKFILL_ACTION))),
            preview_backfill_pending=bool(redis.exists(maintenance_pending_key(active_provider, PREVIEW_BACKFILL_ACTION))),
            near_duplicate_hamming_threshold=get_near_duplicate_threshold(db),
        ),
        meta={},
    )


def build_autoscaler_settings_response(db: DbSession, redis: RedisClient) -> AutoscalerSettingsResponse:
    settings = get_autoscaler_settings(db)
    active_workers = sorted(
        key.removeprefix("nextboo:workers:active:")
        for key in redis.keys("nextboo:workers:active:*")
    )
    queue_depth = int(redis.llen("jobs:ingest:camie"))
    recommended_worker_count = max(
        int(settings["autoscaler_min_workers"]),
        min(
            int(settings["autoscaler_max_workers"]),
            max(1, (queue_depth + int(settings["autoscaler_jobs_per_worker"]) - 1) // int(settings["autoscaler_jobs_per_worker"])),
        ),
    )
    last_status = redis.hgetall("nextboo:autoscaler:status")
    autoscaler_active_workers = []
    if last_status.get("active_workers"):
        try:
            autoscaler_active_workers = json.loads(last_status["active_workers"])
        except Exception:
            autoscaler_active_workers = active_workers
    return AutoscalerSettingsResponse(
        data=AutoscalerSettingsRead(
            autoscaler_enabled=bool(settings["autoscaler_enabled"]),
            autoscaler_jobs_per_worker=int(settings["autoscaler_jobs_per_worker"]),
            autoscaler_min_workers=int(settings["autoscaler_min_workers"]),
            autoscaler_max_workers=int(settings["autoscaler_max_workers"]),
            autoscaler_poll_seconds=int(settings["autoscaler_poll_seconds"]),
            active_workers=autoscaler_active_workers or active_workers,
            current_worker_count=int(last_status.get("current_worker_count") or len(active_workers)),
            queue_depth=int(last_status.get("queue_depth") or queue_depth),
            recommended_worker_count=int(last_status.get("recommended_worker_count") or recommended_worker_count),
            last_scale_action=last_status.get("last_scale_action"),
            last_scale_at=last_status.get("last_scale_at"),
            last_error=last_status.get("last_error") or None,
        ),
        meta={},
    )


def build_upload_pipeline_balancer_settings_response(db: DbSession, redis: RedisClient) -> UploadPipelineBalancerSettingsResponse:
    settings = get_upload_pipeline_balancer_settings(db)
    status = redis.hgetall("nextboo:upload-balancer:status")
    active_workers_by_stage = {
        "scanning": sorted(key.removeprefix("nextboo:upload-stage:scanning:") for key in redis.keys("nextboo:upload-stage:scanning:*")),
        "dedupe": sorted(key.removeprefix("nextboo:upload-stage:dedupe:") for key in redis.keys("nextboo:upload-stage:dedupe:*")),
        "normalize": sorted(key.removeprefix("nextboo:upload-stage:normalize:") for key in redis.keys("nextboo:upload-stage:normalize:*")),
        "dispatch": sorted(key.removeprefix("nextboo:upload-stage:dispatch:") for key in redis.keys("nextboo:upload-stage:dispatch:*")),
        "ingest_image": sorted(key.removeprefix("nextboo:workers:image:active:") for key in redis.keys("nextboo:workers:image:active:*")),
        "ingest_video": sorted(key.removeprefix("nextboo:workers:video:active:") for key in redis.keys("nextboo:workers:video:active:*")),
    }
    stage_rows = []
    for stage in settings["stages"]:
        stage_key = str(stage["stage"])
        recommended = int(status.get(f"{stage_key}:recommended_workers") or stage["min_workers"])
        queue_depth = int(status.get(f"{stage_key}:queue_depth") or 0)
        oldest_seconds = int(status.get(f"{stage_key}:oldest_queued_seconds") or 0)
        current_workers = int(status.get(f"{stage_key}:current_workers") or len(active_workers_by_stage.get(stage_key, [])))
        visible_active_workers = list(active_workers_by_stage.get(stage_key, []))[: max(current_workers, 0)]
        try:
            score = float(status.get(f"{stage_key}:score") or 0)
        except ValueError:
            score = 0
        stage_rows.append(
            {
                **stage,
                "current_workers": current_workers,
                "recommended_workers": recommended,
                "queue_depth": queue_depth,
                "oldest_queued_seconds": oldest_seconds,
                "score": score,
                "active_workers": visible_active_workers,
            }
        )

    return UploadPipelineBalancerSettingsResponse(
        data=UploadPipelineBalancerSettingsRead(
            upload_pipeline_balancer_enabled=bool(settings["upload_pipeline_balancer_enabled"]),
            upload_pipeline_balancer_poll_seconds=int(settings["upload_pipeline_balancer_poll_seconds"]),
            upload_pipeline_balancer_flexible_slots=int(settings["upload_pipeline_balancer_flexible_slots"]),
            stages=stage_rows,
            last_rebalance_at=status.get("last_rebalance_at") or None,
            last_rebalance_summary=status.get("last_rebalance_summary") or None,
            last_error=status.get("last_error") or None,
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
    redis: RedisClient,
    request: Request,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> SidebarSettingsResponse:
    enforce_rate_limit(db, redis, request, "admin_write")
    sanitized = {
        key: max(getattr(payload, key), 0)
        for key in SidebarSettingsRead.model_fields.keys()
    }
    return SidebarSettingsResponse(data=SidebarSettingsRead(**update_sidebar_limits(db, sanitized)), meta={})


@router.get("/rate-limits", response_model=RateLimitSettingsResponse)
def get_rate_limits(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> RateLimitSettingsResponse:
    return RateLimitSettingsResponse(data=RateLimitSettingsRead(**get_rate_limit_settings(db)), meta={})


@router.get("/autoscaler", response_model=AutoscalerSettingsResponse)
def get_autoscaler(
    db: DbSession,
    redis: RedisClient,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> AutoscalerSettingsResponse:
    return build_autoscaler_settings_response(db, redis)


@router.get("/upload-pipeline-balancer", response_model=UploadPipelineBalancerSettingsResponse)
def get_upload_pipeline_balancer(
    db: DbSession,
    redis: RedisClient,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UploadPipelineBalancerSettingsResponse:
    return build_upload_pipeline_balancer_settings_response(db, redis)


@router.patch("/rate-limits", response_model=RateLimitSettingsResponse)
def patch_rate_limits(
    payload: RateLimitSettingsUpdate,
    db: DbSession,
    redis: RedisClient,
    request: Request,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> RateLimitSettingsResponse:
    enforce_rate_limit(db, redis, request, "admin_write")
    sanitized = {
        key: max(getattr(payload, key), 1)
        for key in RateLimitSettingsRead.model_fields.keys()
    }
    return RateLimitSettingsResponse(data=RateLimitSettingsRead(**update_rate_limit_settings(db, sanitized)), meta={})


@router.patch("/autoscaler", response_model=AutoscalerSettingsResponse)
def patch_autoscaler(
    payload: AutoscalerSettingsUpdate,
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> AutoscalerSettingsResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    sanitized = {
        "autoscaler_enabled": payload.autoscaler_enabled,
        "autoscaler_jobs_per_worker": max(payload.autoscaler_jobs_per_worker, 1),
        "autoscaler_min_workers": max(payload.autoscaler_min_workers, 1),
        "autoscaler_max_workers": max(payload.autoscaler_max_workers, 1),
        "autoscaler_poll_seconds": max(payload.autoscaler_poll_seconds, 5),
    }
    update_autoscaler_settings(db, sanitized)
    return build_autoscaler_settings_response(db, redis)


@router.patch("/upload-pipeline-balancer", response_model=UploadPipelineBalancerSettingsResponse)
def patch_upload_pipeline_balancer(
    payload: UploadPipelineBalancerSettingsUpdate,
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UploadPipelineBalancerSettingsResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    sanitized = {
        "upload_pipeline_balancer_enabled": True,
        "upload_pipeline_balancer_poll_seconds": max(payload.upload_pipeline_balancer_poll_seconds, 5),
        "upload_pipeline_balancer_flexible_slots": 0,
        "stages": [
            {
                "stage": stage.stage,
                "min_workers": max(stage.min_workers, 1),
                "max_workers": max(stage.max_workers, 1),
                "jobs_per_worker": max(stage.jobs_per_worker, 1),
            }
            for stage in payload.stages
        ],
    }
    update_upload_pipeline_balancer_settings(db, sanitized)
    redis.set("nextboo:upload-balancer:force", "1", ex=60)
    return build_upload_pipeline_balancer_settings_response(db, redis)


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
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> RetagAllResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
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


@router.post("/tagger/backfill-previews", response_model=PreviewBackfillResponse)
def enqueue_preview_backfill(
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> PreviewBackfillResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    active_provider = get_tagger_provider(db)
    pending_key = maintenance_pending_key(active_provider, PREVIEW_BACKFILL_ACTION)
    running_key = maintenance_running_key(active_provider, PREVIEW_BACKFILL_ACTION)

    if redis.exists(running_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A preview backfill task is already running for the active tagger.",
        )
    if not redis.set(pending_key, "1", nx=True, ex=3600):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A preview backfill task is already queued for the active tagger.",
        )

    queue_name = maintenance_queue_name_for_provider(active_provider)
    payload = QueueMaintenancePayload(
        action=PREVIEW_BACKFILL_ACTION,
        requested_by_user_id=current_user.id,
        requested_by_username=current_user.username,
    )
    redis.rpush(queue_name, payload.model_dump_json())

    db.execute(text("UPDATE app_settings SET updated_at = NOW() WHERE key = :key"), {"key": "tagger_provider"})
    db.commit()
    response = build_tagger_settings_response(db, redis)
    return PreviewBackfillResponse(data=response.data, meta={})


@router.patch("/tagger/near-duplicate-threshold", response_model=TaggerSettingsResponse)
def patch_near_duplicate_threshold(
    value: int,
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TaggerSettingsResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    update_near_duplicate_threshold(db, value)
    return build_tagger_settings_response(db, redis)


@router.get("/tos", response_model=TermsOfServiceResponse)
def get_terms_of_service_settings(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TermsOfServiceResponse:
    return TermsOfServiceResponse(data=TermsOfServiceRead(**get_terms_of_service(db)), meta={})


@router.patch("/tos", response_model=TermsOfServiceResponse)
def patch_terms_of_service_settings(
    payload: TermsOfServiceUpdate,
    db: DbSession,
    redis: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TermsOfServiceResponse:
    enforce_rate_limit(db, redis, request, "admin_write", current_user=current_user)
    updated = update_terms_of_service(db, title=payload.title, paragraphs=payload.paragraphs)
    return TermsOfServiceResponse(data=TermsOfServiceRead(**updated), meta={})
