import secrets
from datetime import datetime, timezone

from app.core.constants import InviteStatus, StrikeSourceType, UserRole
from app.core.security import hash_password
from app.models.invite import UserInvite, UserStrike
from app.models.user import User
from app.services.admin_users import ban_user_email, email_is_banned
from sqlalchemy import func
from sqlalchemy.orm import Session


def normalize_email(value: str) -> str:
    return value.strip().lower()


def can_manage_target(actor: User, target: User) -> bool:
    if actor.role == UserRole.ADMIN:
        return actor.id != target.id
    if actor.role == UserRole.MODERATOR:
        return actor.id != target.id and target.role == UserRole.UPLOADER
    return False


def count_user_strikes(db: Session, user_id: int) -> int:
    return int(db.query(func.count(UserStrike.id)).filter(UserStrike.target_user_id == user_id).scalar() or 0)


def count_used_invites(db: Session, user_id: int) -> int:
    return int(
        db.query(func.count(UserInvite.id))
        .filter(UserInvite.inviter_user_id == user_id, UserInvite.rehabilitated_at.is_(None))
        .scalar()
        or 0
    )


def get_remaining_invites(db: Session, user: User) -> int:
    used = count_used_invites(db, user.id)
    return max(user.invite_quota - used, 0)


def build_invite_code() -> str:
    return secrets.token_urlsafe(24)


def create_invite(db: Session, inviter: User, email: str, note: str | None = None) -> UserInvite:
    normalized_email = normalize_email(email)
    if email_is_banned(db, normalized_email):
        raise ValueError("Email address is banned")
    if db.query(User).filter(User.email == normalized_email).first():
        raise ValueError("Email address is already registered")
    existing = (
        db.query(UserInvite)
        .filter(UserInvite.email == normalized_email, UserInvite.status == InviteStatus.PENDING)
        .first()
    )
    if existing:
        raise ValueError("An active invite for this email already exists")
    if get_remaining_invites(db, inviter) <= 0:
        raise ValueError("No invites remaining")

    invite = UserInvite(
        code=build_invite_code(),
        email=normalized_email,
        note=note.strip() if note else None,
        status=InviteStatus.PENDING,
        inviter_user_id=inviter.id,
    )
    db.add(invite)
    db.flush()
    return invite


def create_admin_bootstrap_invite(
    db: Session,
    *,
    note: str,
    invite_quota: int = 50,
) -> UserInvite:
    invite = UserInvite(
        code=build_invite_code(),
        email=None,
        note=note.strip(),
        status=InviteStatus.PENDING,
        inviter_user_id=None,
        granted_role=UserRole.ADMIN,
        grant_can_upload=True,
        grant_can_view_explicit=True,
        grant_invite_quota=invite_quota,
    )
    db.add(invite)
    db.flush()
    return invite


def redeem_invite(db: Session, *, code: str, email: str, username: str, password: str) -> User:
    normalized_email = normalize_email(email)
    invite = db.query(UserInvite).filter(UserInvite.code == code, UserInvite.status == InviteStatus.PENDING).first()
    if not invite:
        raise ValueError("Invite code is invalid")
    if invite.email and invite.email != normalized_email:
        raise ValueError("Invite email does not match")
    inviter = db.get(User, invite.inviter_user_id) if invite.inviter_user_id else None
    if invite.inviter_user_id and (not inviter or not inviter.is_active or inviter.is_banned):
        raise ValueError("Inviter account is no longer eligible")
    if not inviter and invite.granted_role is None:
        raise ValueError("Invite is missing inviter context")
    if email_is_banned(db, normalized_email):
        raise ValueError("Email address is banned")
    if db.query(User).filter(User.username == username).first():
        raise ValueError("Username already exists")
    if db.query(User).filter(User.email == normalized_email).first():
        raise ValueError("Email address is already registered")

    granted_role = invite.granted_role or UserRole.UPLOADER
    can_upload = invite.grant_can_upload or granted_role in {UserRole.ADMIN, UserRole.MODERATOR}
    can_view_explicit = invite.grant_can_view_explicit or granted_role == UserRole.ADMIN
    invite_quota = invite.grant_invite_quota if invite.grant_invite_quota is not None else 2

    user = User(
        username=username.strip(),
        email=normalized_email,
        password_hash=hash_password(password),
        role=granted_role,
        invited_by_user_id=inviter.id if inviter else None,
        invite_quota=invite_quota,
        is_active=True,
        is_banned=False,
        can_upload=can_upload,
        can_view_questionable=True,
        can_view_explicit=can_view_explicit,
    )
    db.add(user)
    db.flush()

    invite.status = InviteStatus.ACCEPTED
    invite.invited_user_id = user.id
    invite.accepted_at = datetime.now(timezone.utc)
    db.add(invite)
    db.flush()
    return user


def delete_pending_invite(db: Session, *, invite: UserInvite, current_user: User) -> None:
    if invite.inviter_user_id != current_user.id:
        raise ValueError("You cannot delete this invite")
    if invite.status != InviteStatus.PENDING:
        raise ValueError("Only pending invites can be deleted")
    db.delete(invite)
    db.flush()


def list_user_invites(db: Session, user_id: int) -> list[UserInvite]:
    return (
        db.query(UserInvite)
        .filter(UserInvite.inviter_user_id == user_id)
        .order_by(UserInvite.created_at.desc())
        .all()
    )


def rehab_revoked_invite(db: Session, *, invite: UserInvite, admin_user: User) -> UserInvite:
    if admin_user.role != UserRole.ADMIN:
        raise ValueError("Only admins can rehab invites")
    if invite.status != InviteStatus.REVOKED:
        raise ValueError("Only revoked invites can be rehabilitated")
    if invite.rehabilitated_at is not None:
        raise ValueError("Invite has already been rehabilitated")
    invite.rehabilitated_at = datetime.now(timezone.utc)
    invite.rehabilitated_by_user_id = admin_user.id
    db.add(invite)
    db.flush()
    return invite


def issue_strike(
    db: Session,
    *,
    target_user: User,
    issued_by_user: User | None,
    reason: str,
    source: StrikeSourceType,
    related_user: User | None = None,
) -> UserStrike:
    strike = UserStrike(
        target_user_id=target_user.id,
        issued_by_user_id=issued_by_user.id if issued_by_user else None,
        related_user_id=related_user.id if related_user else None,
        source=source,
        reason=reason.strip(),
    )
    db.add(strike)
    db.flush()

    if count_user_strikes(db, target_user.id) >= 3 and not target_user.is_banned:
        ban_user_with_enforcement(
            db,
            target_user=target_user,
            actor_user=issued_by_user,
            reason=f"Automatic ban after accumulating 3 strikes. Latest strike: {reason.strip()}",
            propagate_inviter=True,
        )
    return strike


def ban_user_with_enforcement(
    db: Session,
    *,
    target_user: User,
    actor_user: User | None,
    reason: str | None = None,
    propagate_inviter: bool = True,
) -> User:
    if target_user.is_banned:
        return target_user

    target_user.is_banned = True
    target_user.is_active = False
    target_user.can_upload = False
    ban_user_email(db, target_user, actor_user.id if actor_user else None, reason)
    db.add(target_user)
    db.flush()

    invite = (
        db.query(UserInvite)
        .filter(UserInvite.invited_user_id == target_user.id, UserInvite.status == InviteStatus.ACCEPTED)
        .first()
    )
    if invite and invite.revoked_at is None:
        invite.status = InviteStatus.REVOKED
        invite.revoked_at = datetime.now(timezone.utc)
        db.add(invite)
        db.flush()

    inviter = target_user.invited_by
    if propagate_inviter and inviter and inviter.id != target_user.id:
        strike_reason = (
            f"Invited user {target_user.username} was banned."
            if not reason
            else f"Invited user {target_user.username} was banned. Reason: {reason}"
        )
        issue_strike(
            db,
            target_user=inviter,
            issued_by_user=actor_user,
            reason=strike_reason,
            source=StrikeSourceType.INVITEE_BAN,
            related_user=target_user,
        )

    return target_user
