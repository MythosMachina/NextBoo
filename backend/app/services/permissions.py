from typing import Annotated

from app.api.deps import get_current_user
from app.core.constants import UserRole
from app.models.user import User
from fastapi import Depends, HTTPException, status


def require_upload_access(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role in {UserRole.ADMIN, UserRole.MODERATOR} or current_user.can_upload:
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload permission required")
