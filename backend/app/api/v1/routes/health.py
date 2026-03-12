from app.api.deps import DbSession, RedisClient
from app.core.config import get_settings
from app.schemas.health import HealthResponse
from fastapi import APIRouter
from sqlalchemy import text


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def healthcheck(db: DbSession, redis_client: RedisClient) -> HealthResponse:
    settings = get_settings()
    db.execute(text("SELECT 1"))
    redis_ok = bool(redis_client.ping())
    return HealthResponse(
        data={
            "status": "ok",
            "service": "backend",
            "environment": settings.app_env,
            "database": "ok",
            "redis": "ok" if redis_ok else "unreachable",
        },
        meta={"project_name": settings.project_name},
    )
