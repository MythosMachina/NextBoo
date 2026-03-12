from pydantic import BaseModel


class SidebarSettingsRead(BaseModel):
    sidebar_general_limit: int
    sidebar_meta_limit: int
    sidebar_character_limit: int
    sidebar_artist_limit: int
    sidebar_series_limit: int
    sidebar_creature_limit: int


class SidebarSettingsUpdate(BaseModel):
    sidebar_general_limit: int
    sidebar_meta_limit: int
    sidebar_character_limit: int
    sidebar_artist_limit: int
    sidebar_series_limit: int
    sidebar_creature_limit: int


class SidebarSettingsResponse(BaseModel):
    data: SidebarSettingsRead
    meta: dict[str, str] = {}


class TaggerSettingsRead(BaseModel):
    provider: str
    retag_all_running: bool = False
    retag_all_pending: bool = False


class TaggerSettingsResponse(BaseModel):
    data: TaggerSettingsRead
    meta: dict[str, str] = {}


class RetagAllResponse(BaseModel):
    data: TaggerSettingsRead
    meta: dict[str, str] = {}
