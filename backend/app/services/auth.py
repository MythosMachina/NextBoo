from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.security import create_token, verify_password
from app.models.user import User
from app.services.tos import purge_expired_tos_deactivated_users
from sqlalchemy.orm import Session


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    purge_expired_tos_deactivated_users(db)
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash) or not user.is_active or user.is_banned:
        return None
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def build_token_response(user: User) -> dict[str, str]:
    settings = get_settings()
    access_token = create_token(
        subject=str(user.id),
        token_type="access",
        expires_minutes=settings.access_token_expire_minutes,
        extra_claims={"role": user.role.value},
    )
    refresh_token = create_token(
        subject=str(user.id),
        token_type="refresh",
        expires_minutes=settings.refresh_token_expire_minutes,
        extra_claims={"role": user.role.value},
    )
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
