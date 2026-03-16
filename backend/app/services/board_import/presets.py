from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from app.services.board_import.models import BoardPreset


DATA_ROOT = Path(__file__).resolve().parent / "data"
HYDRUS_WIN_SWEEP_CSV = DATA_ROOT / "hydrus-preset-sweep-win.csv"


CORE_PRESETS: dict[str, BoardPreset] = {
    "E621": BoardPreset(
        name="E621",
        family="e621-like",
        site_url="https://e621.net",
        search_url="https://e621.net/posts.json",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/E621/e621-api-2024-12-05.png",
    ),
    "E926": BoardPreset(
        name="E926",
        family="e621-like",
        site_url="https://e926.net",
        search_url="https://e621.net/posts.json",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/E926/e926_tag_search_2018.09.20.png",
    ),
    "DANBOORU": BoardPreset(
        name="Danbooru",
        family="danbooru-like",
        site_url="https://danbooru.donmai.us",
        search_url="https://danbooru.donmai.us/posts.json",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/nGUG/danbooru_both_2018.09.20.png",
    ),
    "SAFEBOORU": BoardPreset(
        name="Safebooru",
        family="gelbooru-like",
        site_url="https://safebooru.org",
        search_url="https://safebooru.org/index.php",
        hydrus_reference=None,
    ),
    "XBOORU": BoardPreset(
        name="Xbooru",
        family="gelbooru-like",
        site_url="https://xbooru.com",
        search_url="https://xbooru.com/index.php",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/Xbooru/xbooru_tag_search_2018.09.20.png",
    ),
    "RULE34": BoardPreset(
        name="Rule34",
        family="gelbooru-like",
        site_url="https://rule34.xxx",
        search_url="https://rule34.xxx/index.php",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/rule34.xxx api - 2021-06-14.png",
    ),
    "YANDE.RE": BoardPreset(
        name="Yande.re",
        family="moebooru-like",
        site_url="https://yande.re",
        search_url="https://yande.re/post.json",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/yande.re-tag-search-2018.09.22.png",
    ),
    "KONACHAN": BoardPreset(
        name="Konachan",
        family="moebooru-like",
        site_url="https://konachan.com",
        search_url="https://konachan.com/post.json",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/konachan.com_pool-download-2025.02.17.png",
    ),
    "KONACHAN.NET": BoardPreset(
        name="Konachan.net",
        family="moebooru-like",
        site_url="https://konachan.net",
        search_url="https://konachan.net/post.json",
        hydrus_reference="docs/external/Hydrus-Presets-and-Scripts/Downloaders/konachan.net_pool-download-2025.02.17.png",
    ),
}


def _normalize_key(name: str) -> str:
    return name.upper()


@lru_cache(maxsize=1)
def load_discovered_winner_catalog() -> list[dict[str, str | bool]]:
    catalog: list[dict[str, str | bool]] = []
    if not HYDRUS_WIN_SWEEP_CSV.exists():
        return catalog

    with HYDRUS_WIN_SWEEP_CSV.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candidate_url = row["candidate_url"]
            parsed = urlparse(candidate_url)
            host = parsed.netloc.lower()
            import_name = ""
            family = ""
            supported = False

            if host.endswith(".booru.org") and "page=post&s=list" in candidate_url:
                import_name = host
                family = "gelbooru-like"
                supported = True
            elif host in {"e621.net", "e926.net", "danbooru.donmai.us", "xbooru.com", "safebooru.org", "rule34.xxx", "yande.re", "konachan.com", "konachan.net"}:
                # already represented by curated core presets
                import_name = host
                supported = True

            catalog.append(
                {
                    "name": import_name or Path(row["preset_path"]).stem,
                    "preset_path": row["preset_path"],
                    "source_group": row["source_group"],
                    "candidate_url": candidate_url,
                    "http_status": row["http_status"],
                    "supported": supported,
                    "family": family,
                }
            )

    return catalog


@lru_cache(maxsize=1)
def build_generated_presets() -> dict[str, BoardPreset]:
    generated: dict[str, BoardPreset] = {}
    for item in load_discovered_winner_catalog():
        if not item["supported"]:
            continue
        if item["family"] != "gelbooru-like":
            continue

        name = str(item["name"])
        if not name.endswith(".booru.org"):
            continue
        key = _normalize_key(name)
        if key in CORE_PRESETS or key in generated:
            continue
        site_url = f"https://{name}"
        generated[key] = BoardPreset(
            name=name,
            family="gelbooru-like",
            site_url=site_url,
            search_url=f"{site_url}/index.php",
            hydrus_reference=f"docs/external/Hydrus-Presets-and-Scripts/Downloaders/{item['preset_path']}",
        )
    return generated


PRESETS: dict[str, BoardPreset] = {
    **CORE_PRESETS,
}


def get_preset(name: str) -> BoardPreset:
    try:
        return PRESETS[_normalize_key(name)]
    except KeyError as exc:
        available = ", ".join(sorted(PRESETS))
        raise ValueError(f"Unknown booru '{name}'. Available presets: {available}") from exc
