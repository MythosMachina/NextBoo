from typing import Annotated

from app.api.deps import DbSession, require_roles
from app.core.constants import StrikeSourceType, UserRole
from app.models.invite import UserStrike
from app.models.user import User
from app.schemas.strike import StrikeBanRequest, StrikeCreate, StrikeEnvelope, StrikeResponse, StrikesEnvelope
from app.services.social_gate import ban_user_with_enforcement, can_manage_target, issue_strike
from fastapi import APIRouter, Depends, HTTPException, status


router = APIRouter(prefix="/strikes")


def _build_strike_response(strike: UserStrike) -> StrikeResponse:
    return StrikeResponse(
        id=strike.id,
        target_username=strike.target_user.username,
        issued_by_username=strike.issued_by_user.username if strike.issued_by_user else None,
        related_username=strike.related_user.username if strike.related_user else None,
        source=strike.source,
        reason=strike.reason,
        created_at=strike.created_at,
    )


@router.get("", response_model=StrikesEnvelope)
def list_strikes(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> StrikesEnvelope:
    strikes = db.query(UserStrike).order_by(UserStrike.created_at.desc()).limit(200).all()
    return StrikesEnvelope(data=[_build_strike_response(strike) for strike in strikes], meta={"count": len(strikes)})


@router.post("", response_model=StrikeEnvelope, status_code=status.HTTP_201_CREATED)
def create_strike(
    payload: StrikeCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> StrikeEnvelope:
    target_user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not can_manage_target(current_user, target_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot issue strike for this account")
    strike = issue_strike(
        db,
        target_user=target_user,
        issued_by_user=current_user,
        reason=payload.reason,
        source=StrikeSourceType.MANUAL,
    )
    db.commit()
    db.refresh(strike)
    return StrikeEnvelope(data=_build_strike_response(strike), meta={})


@router.post("/ban")
def ban_by_username(
    payload: StrikeBanRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict:
    target_user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not can_manage_target(current_user, target_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot ban this account")
    ban_user_with_enforcement(db, target_user=target_user, actor_user=current_user, reason=payload.reason, propagate_inviter=True)
    db.commit()
    return {"data": {"status": "banned", "username": target_user.username}, "meta": {}}
