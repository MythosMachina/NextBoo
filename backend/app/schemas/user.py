from datetime import datetime

from app.core.constants import ProcessingStatus, Rating, UserRole, VisibilityStatus
from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.UPLOADER


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    is_banned: bool | None = None
    can_upload: bool | None = None
    invite_quota: int | None = None
    can_view_questionable: bool | None = None
    can_view_explicit: bool | None = None


class UserProfileUpdate(BaseModel):
    can_view_questionable: bool | None = None
    can_view_explicit: bool | None = None
    tag_blacklist: list[str] | None = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr | None
    role: UserRole
    is_active: bool
    is_banned: bool
    can_upload: bool
    invite_quota: int
    invite_slots_used: int
    invite_slots_remaining: int
    invited_by_username: str | None = None
    strike_count: int
    can_view_questionable: bool
    can_view_explicit: bool
    tag_blacklist: list[str] = []


class AdminUserPasswordReset(BaseModel):
    new_password: str | None = None


class AdminUserBan(BaseModel):
    reason: str | None = None


class UsersEnvelope(BaseModel):
    data: list[UserResponse]
    meta: dict[str, int | str] = {}


class PublicUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    created_at: datetime


class PublicUserProfileImage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    uuid_short: str
    original_filename: str
    width: int
    height: int
    rating: Rating
    processing_status: ProcessingStatus
    created_at: datetime
    visibility_status: VisibilityStatus = VisibilityStatus.VISIBLE
    thumb_url: str | None = None


class PublicUserProfileEnvelope(BaseModel):
    data: PublicUserResponse
    uploads: list[PublicUserProfileImage]
    meta: dict[str, int | str | None]
