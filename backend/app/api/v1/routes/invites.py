from typing import Annotated

from app.api.deps import DbSession, get_current_user, require_roles
from app.core.constants import UserRole
from app.models.invite import UserInvite
from app.models.user import User
from app.schemas.auth import LoginResponse, TokenResponse
from app.schemas.invite import InviteCreate, InviteDashboard, InviteDashboardEnvelope, InviteRedeem, InviteResponse
from app.schemas.app_settings import TermsOfServiceRead, TermsOfServiceResponse
from app.services.auth import build_token_response
from app.services.app_settings import get_terms_of_service, update_terms_of_service
from app.services.social_gate import (
    count_used_invites,
    create_invite,
    delete_pending_invite,
    get_remaining_invites,
    list_user_invites,
    redeem_invite,
    rehab_revoked_invite,
)
from fastapi import APIRouter, Depends, HTTPException, status


router = APIRouter(prefix="/invites")


def _build_invite_response(invite: UserInvite) -> InviteResponse:
    invited_username = invite.invited_user.username if invite.invited_user else None
    return InviteResponse(
        id=invite.id,
        code=invite.code,
        email=invite.email,
        note=invite.note,
        status=invite.status,
        invited_username=invited_username,
        created_at=invite.created_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        rehabilitated_at=invite.rehabilitated_at,
    )


@router.get("/tos", response_model=TermsOfServiceResponse)
def get_public_terms_of_service(db: DbSession) -> TermsOfServiceResponse:
    return TermsOfServiceResponse(data=TermsOfServiceRead(**get_terms_of_service(db)), meta={})


@router.get("/me", response_model=InviteDashboardEnvelope)
def get_my_invites(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> InviteDashboardEnvelope:
    invites = list_user_invites(db, current_user.id)
    used = count_used_invites(db, current_user.id)
    remaining = get_remaining_invites(db, current_user)
    return InviteDashboardEnvelope(
        data=InviteDashboard(
            quota=current_user.invite_quota,
            used=used,
            remaining=remaining,
            invited_by_username=current_user.invited_by.username if current_user.invited_by else None,
            invites=[_build_invite_response(invite) for invite in invites],
        ),
        meta={"count": len(invites)},
    )


@router.post("/me", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
def create_my_invite(
    payload: InviteCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> InviteResponse:
    if current_user.role not in {UserRole.ADMIN, UserRole.MODERATOR, UserRole.UPLOADER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite creation not allowed")
    try:
        invite = create_invite(db, current_user, payload.email, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(invite)
    return _build_invite_response(invite)


@router.delete("/me/{invite_id}")
def delete_my_pending_invite(
    invite_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    invite = db.get(UserInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    try:
        delete_pending_invite(db, invite=invite, current_user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return {"data": {"status": "deleted"}, "meta": {}}


@router.delete("/admin/{invite_id}")
def delete_pending_invite_admin(
    invite_id: int,
    db: DbSession,
    current_admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    invite = db.get(UserInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    try:
        delete_pending_invite(db, invite=invite, current_user=invite.inviter)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return {"data": {"status": "deleted", "acted_by": current_admin.username}, "meta": {}}


@router.get("/admin/user/{user_id}", response_model=InviteDashboardEnvelope)
def get_user_invites_admin(
    user_id: int,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> InviteDashboardEnvelope:
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    invites = list_user_invites(db, target_user.id)
    used = count_used_invites(db, target_user.id)
    remaining = get_remaining_invites(db, target_user)
    return InviteDashboardEnvelope(
        data=InviteDashboard(
            quota=target_user.invite_quota,
            used=used,
            remaining=remaining,
            invited_by_username=target_user.invited_by.username if target_user.invited_by else None,
            invites=[_build_invite_response(invite) for invite in invites],
        ),
        meta={"count": len(invites), "user_id": user_id, "username": target_user.username},
    )


@router.post("/admin/{invite_id}/rehab")
def rehab_invite_admin(
    invite_id: int,
    db: DbSession,
    current_admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    invite = db.get(UserInvite, invite_id)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    try:
        rehab_revoked_invite(db, invite=invite, admin_user=current_admin)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return {"data": {"status": "rehabilitated"}, "meta": {}}


@router.post("/redeem", response_model=LoginResponse)
def redeem_user_invite(payload: InviteRedeem, db: DbSession) -> LoginResponse:
    if len(payload.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")
    try:
        user = redeem_invite(
            db,
            code=payload.code,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            accepted_tos=payload.accepted_tos,
            tos_version=payload.tos_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(user)
    return LoginResponse(data=TokenResponse(**build_token_response(user)), meta={})
