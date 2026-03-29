from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RemotePost:
    board: str
    post_id: str
    file_url: str
    filename: str
    mime_type: str | None = None
    tags: list[str] = field(default_factory=list)
    source_url: str | None = None
    md5: str | None = None


@dataclass(slots=True)
class BoardPreset:
    name: str
    family: str
    site_url: str
    search_url: str
    hydrus_reference: str | None = None
    user_agent: str = "borooimport/0.1 (+https://github.com/MythosMachina/NextBoo)"
