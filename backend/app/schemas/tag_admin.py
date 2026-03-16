from datetime import datetime

from app.core.constants import AliasType, TagCategory
from pydantic import BaseModel


class TagAdminRead(BaseModel):
    id: int
    name_normalized: str
    display_name: str
    category: TagCategory
    is_active: bool
    is_locked: bool
    alias_count: int
    image_count: int
    is_name_pattern: bool


class TagAdminEnvelope(BaseModel):
    data: list[TagAdminRead]
    meta: dict[str, int | str | None]


class TagUpdatePayload(BaseModel):
    display_name: str | None = None
    category: TagCategory | None = None
    is_active: bool | None = None
    is_locked: bool | None = None


class TagAliasUpsert(BaseModel):
    alias_name: str
    target_tag_name: str
    alias_type: AliasType = AliasType.SYNONYM


class TagMergePayload(BaseModel):
    source_tag_name: str
    target_tag_name: str
    reason: str | None = None


class DangerTagRead(BaseModel):
    id: int
    tag_id: int
    tag_name: str
    display_name: str
    reason: str | None
    is_enabled: bool
    created_at: datetime


class DangerTagEnvelope(BaseModel):
    data: list[DangerTagRead]
    meta: dict[str, int | str | None]


class DangerTagUpsert(BaseModel):
    tag_name: str
    reason: str | None = None
    is_enabled: bool = True
