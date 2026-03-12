from datetime import datetime

from app.core.constants import StrikeSourceType
from pydantic import BaseModel


class StrikeCreate(BaseModel):
    username: str
    reason: str


class StrikeBanRequest(BaseModel):
    username: str
    reason: str | None = None


class StrikeResponse(BaseModel):
    id: int
    target_username: str
    issued_by_username: str | None = None
    related_username: str | None = None
    source: StrikeSourceType
    reason: str
    created_at: datetime


class StrikeEnvelope(BaseModel):
    data: StrikeResponse
    meta: dict[str, int | str] = {}


class StrikesEnvelope(BaseModel):
    data: list[StrikeResponse]
    meta: dict[str, int | str] = {}
