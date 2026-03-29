from __future__ import annotations

import mimetypes
from pathlib import Path

import requests

from app.services.board_import.models import BoardPreset, RemotePost


class BaseAdapter:
    def __init__(self, preset: BoardPreset) -> None:
        self.preset = preset
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": preset.user_agent,
                "Accept": "application/json",
            }
        )

    @staticmethod
    def normalize_tag(tag: str) -> str:
        return tag.strip().lower().replace(" ", "_")

    @staticmethod
    def dedupe_tags(tags: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            normalized = BaseAdapter.normalize_tag(tag)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def filename_from_url(url: str, fallback: str) -> str:
        return Path(url).name or fallback

    @staticmethod
    def mime_type_from_filename(filename: str) -> str | None:
        return mimetypes.guess_type(filename)[0]

    def search_posts(self, tags: list[str], limit: int) -> list[RemotePost]:
        raise NotImplementedError()
