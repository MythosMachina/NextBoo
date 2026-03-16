from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.constants import UserRole
from app.models.user import User
from app.services.app_settings import get_terms_of_service
from sqlalchemy.orm import Session


TOS_DELETION_GRACE_DAYS = 14


def get_current_tos_version(db: Session) -> str:
    return str(get_terms_of_service(db)["version"])


def user_requires_tos_acceptance(db: Session, user: User | None) -> bool:
    if not user or user.role == UserRole.ADMIN or user.role == UserRole.TOS_DEACTIVATED:
        return False
    return (user.accepted_tos_version or "").strip() != get_current_tos_version(db)


def accept_terms_of_service(db: Session, user: User) -> User:
    current_version = get_current_tos_version(db)
    user.accepted_tos_at = datetime.now(timezone.utc)
    user.accepted_tos_version = current_version
    db.add(user)
    db.flush()
    return user


def decline_terms_of_service(db: Session, user: User) -> User:
    now = datetime.now(timezone.utc)
    user.tos_restore_role = user.role.value
    user.tos_restore_can_upload = user.can_upload
    user.tos_restore_can_view_questionable = user.can_view_questionable
    user.tos_restore_can_view_explicit = user.can_view_explicit
    user.role = UserRole.TOS_DEACTIVATED
    user.can_upload = False
    user.can_view_questionable = False
    user.can_view_explicit = False
    user.tos_declined_at = now
    user.tos_delete_after_at = now + timedelta(days=TOS_DELETION_GRACE_DAYS)
    db.add(user)
    db.flush()
    return user


def purge_expired_tos_deactivated_users(db: Session) -> int:
    now = datetime.now(timezone.utc)
    users = (
        db.query(User)
        .filter(
            User.role == UserRole.TOS_DEACTIVATED,
            User.tos_delete_after_at.is_not(None),
            User.tos_delete_after_at <= now,
        )
        .all()
    )
    count = 0
    for user in users:
        db.delete(user)
        count += 1
    if count:
        db.commit()
    return count
