from typing import Annotated

from app.api.deps import DbSession, RedisClient, get_current_user, get_current_user_raw
from app.core.constants import UserRole
from app.models.user import User
from app.core.security import decode_token
from app.schemas.auth import LoginResponse, MeResponse, RefreshRequest, TokenResponse, UserRead
from app.services.rate_limits import enforce_rate_limit
from app.services.auth import authenticate_user, build_token_response
from app.services.social_gate import count_used_invites, count_user_strikes
from app.services.tos import accept_terms_of_service, decline_terms_of_service, get_current_tos_version, purge_expired_tos_deactivated_users, user_requires_tos_acceptance
from app.services.user_preferences import parse_user_tag_blacklist
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter(prefix="/auth")


@router.post("/login", response_model=LoginResponse)
def login(
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> LoginResponse:
    enforce_rate_limit(db, redis_client, request, "login")
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return LoginResponse(data=TokenResponse(**build_token_response(user)), meta={})


@router.post("/refresh", response_model=LoginResponse)
def refresh(db: DbSession, redis_client: RedisClient, request: Request, payload: RefreshRequest) -> LoginResponse:
    enforce_rate_limit(db, redis_client, request, "login")
    purge_expired_tos_deactivated_users(db)
    try:
        token_payload = decode_token(payload.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user = db.get(User, int(token_payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return LoginResponse(data=TokenResponse(**build_token_response(user)), meta={})


@router.get("/me", response_model=MeResponse)
def me(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user_raw)],
) -> MeResponse:
    invite_slots_used = count_used_invites(db, current_user.id)
    current_tos_version = get_current_tos_version(db)
    user = UserRead(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        can_upload=current_user.can_upload or current_user.role in {UserRole.ADMIN, UserRole.MODERATOR},
        invite_quota=current_user.invite_quota,
        invite_slots_used=invite_slots_used,
        invite_slots_remaining=max(current_user.invite_quota - invite_slots_used, 0),
        invited_by_username=current_user.invited_by.username if current_user.invited_by else None,
        strike_count=count_user_strikes(db, current_user.id),
        can_view_questionable=current_user.can_view_questionable,
        can_view_explicit=current_user.can_view_explicit,
        tag_blacklist=parse_user_tag_blacklist(current_user),
        requires_tos_acceptance=user_requires_tos_acceptance(db, current_user),
        accepted_tos_version=current_user.accepted_tos_version,
        current_tos_version=current_tos_version,
        tos_declined_at=current_user.tos_declined_at.isoformat() if current_user.tos_declined_at else None,
        tos_delete_after_at=current_user.tos_delete_after_at.isoformat() if current_user.tos_delete_after_at else None,
    )
    return MeResponse(data=user, meta={})


@router.post("/tos/accept", response_model=MeResponse)
def accept_current_tos(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user_raw)],
) -> MeResponse:
    if current_user.role == UserRole.TOS_DEACTIVATED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Backup-only accounts cannot be reactivated")
    accept_terms_of_service(db, current_user)
    db.commit()
    db.refresh(current_user)
    return me(db, current_user)


@router.post("/tos/decline", response_model=MeResponse)
def decline_current_tos(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user_raw)],
) -> MeResponse:
    if current_user.role == UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Administrators cannot enter ToS deactivated mode")
    decline_terms_of_service(db, current_user)
    db.commit()
    db.refresh(current_user)
    return me(db, current_user)
