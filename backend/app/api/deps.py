from typing import Annotated

from app.core.constants import UserRole
from app.core.security import decode_token
from app.db.session import get_db_session, get_redis_client
from app.models.user import User
from app.services.tos import purge_expired_tos_deactivated_users, user_requires_tos_acceptance
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from redis import Redis
from sqlalchemy.orm import Session


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DbSession = Annotated[Session, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis_client)]


def _resolve_authenticated_user(db: DbSession, token: str) -> User:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")

    purge_expired_tos_deactivated_users(db)
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user


def get_current_user_raw(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    return _resolve_authenticated_user(db, token)


def get_current_user(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    user = _resolve_authenticated_user(db, token)
    if user.role == UserRole.TOS_DEACTIVATED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is in Terms of Service backup-only mode")
    if user_requires_tos_acceptance(db, user):
        raise HTTPException(status_code=428, detail="Terms of Service re-acceptance required")
    return user


def get_optional_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(optional_oauth2_scheme)],
) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None
    purge_expired_tos_deactivated_users(db)
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        return None
    if user.role == UserRole.TOS_DEACTIVATED or user_requires_tos_acceptance(db, user):
        return None
    return user


def require_roles(*roles: UserRole):
    def _require_role(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return _require_role
