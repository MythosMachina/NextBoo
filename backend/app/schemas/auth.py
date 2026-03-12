from app.core.constants import UserRole
from pydantic import BaseModel, ConfigDict, EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    data: TokenResponse
    meta: dict[str, str] = {}


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr | None
    role: UserRole
    is_active: bool
    can_upload: bool
    invite_quota: int
    invite_slots_used: int
    invite_slots_remaining: int
    invited_by_username: str | None = None
    strike_count: int
    can_view_questionable: bool
    can_view_explicit: bool
    tag_blacklist: list[str] = []


class MeResponse(BaseModel):
    data: UserRead
    meta: dict[str, str] = {}
