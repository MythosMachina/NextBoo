from dataclasses import dataclass

from app.api.deps import RedisClient
from app.models.user import User
from app.services.app_settings import get_rate_limit_settings
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session


@dataclass(slots=True)
class RateLimitRule:
    scope: str
    max_requests: int
    window_seconds: int


def build_rate_limit_rule(db: Session, scope: str) -> RateLimitRule:
    settings = get_rate_limit_settings(db)
    max_requests = settings[f"rate_limit_{scope}_max_requests"]
    window_seconds = settings[f"rate_limit_{scope}_window_seconds"]
    return RateLimitRule(scope=scope, max_requests=max_requests, window_seconds=window_seconds)


def identify_rate_limit_subject(request: Request, current_user: User | None = None) -> str:
    if current_user is not None:
        return f"user:{current_user.id}"
    host = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        host = forwarded_for.split(",", 1)[0].strip() or host
    return f"ip:{host}"


def enforce_rate_limit(
    db: Session,
    redis_client: RedisClient,
    request: Request,
    scope: str,
    current_user: User | None = None,
) -> None:
    rule = build_rate_limit_rule(db, scope)
    subject = identify_rate_limit_subject(request, current_user=current_user)
    key = f"nextboo:ratelimit:{scope}:{subject}"
    request_count = redis_client.incr(key)
    if request_count == 1:
        redis_client.expire(key, rule.window_seconds)
    if request_count <= rule.max_requests:
        return
    retry_after = redis_client.ttl(key)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit exceeded for {scope}. Retry in {max(retry_after, 1)} seconds.",
        headers={"Retry-After": str(max(retry_after, 1))},
    )
