from datetime import datetime

from app.core.constants import InviteStatus
from pydantic import BaseModel, ConfigDict, EmailStr


class InviteCreate(BaseModel):
    email: EmailStr
    note: str | None = None


class InviteRedeem(BaseModel):
    code: str
    email: EmailStr
    username: str
    password: str


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    email: EmailStr | None
    note: str | None
    status: InviteStatus
    invited_username: str | None = None
    created_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    rehabilitated_at: datetime | None = None


class InviteDashboard(BaseModel):
    quota: int
    used: int
    remaining: int
    invited_by_username: str | None = None
    invites: list[InviteResponse]


class InviteDashboardEnvelope(BaseModel):
    data: InviteDashboard
    meta: dict[str, int | str | None] = {}
