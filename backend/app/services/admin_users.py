import secrets

from app.models.user import BannedEmail, User
from sqlalchemy.orm import Session


def generate_temp_password() -> str:
    return secrets.token_urlsafe(9)


def email_is_banned(db: Session, email: str | None) -> bool:
    if not email:
        return False
    normalized = email.strip().lower()
    return db.query(BannedEmail).filter(BannedEmail.email == normalized).first() is not None


def ban_user_email(db: Session, user: User, actor_id: int | None, reason: str | None = None) -> None:
    if not user.email:
        return
    normalized = user.email.strip().lower()
    existing = db.query(BannedEmail).filter(BannedEmail.email == normalized).first()
    if existing:
        existing.reason = reason
        existing.banned_by_user_id = actor_id
        db.add(existing)
        return
    db.add(BannedEmail(email=normalized, reason=reason, banned_by_user_id=actor_id))
