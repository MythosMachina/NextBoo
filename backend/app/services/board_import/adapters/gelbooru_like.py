from __future__ import annotations

import html
import re
import time
from urllib.parse import urljoin

from app.services.board_import.adapters.common import BaseAdapter
from app.services.board_import.models import RemotePost


class GelbooruLikeAdapter(BaseAdapter):
    def search_posts(self, tags: list[str], limit: int) -> list[RemotePost]:
        if self.preset.name.lower() == "rule34":
            return self._search_rule34_html(tags, limit)
        if self.preset.site_url.lower().endswith(".booru.org"):
            return self._search_booru_org_html(tags, limit)

        remaining = limit
        page = 0
        results: list[RemotePost] = []
        tag_query = " ".join(tags)

        while remaining > 0:
            page_size = min(100, remaining)
            response = self.session.get(
                self.preset.search_url,
                params={
                    "page": "dapi",
                    "s": "post",
                    "q": "index",
                    "json": "1",
                    "limit": page_size,
                    "pid": page,
                    "tags": tag_query,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            posts = self._extract_posts(payload)
            if not posts:
                break

            for post in posts:
                file_url = post.get("file_url")
                if not file_url:
                    continue
                post_id = str(post["id"])
                results.append(
                    RemotePost(
                        board=self.preset.name,
                        post_id=post_id,
                        file_url=file_url,
                        filename=self.filename_from_url(file_url, post_id),
                        tags=self.dedupe_tags((post.get("tags") or "").split()),
                        source_url=f"{self.preset.site_url.rstrip('/')}/index.php?page=post&s=view&id={post_id}",
                        md5=post.get("md5"),
                    )
                )
                remaining -= 1
                if remaining <= 0:
                    break

            if len(posts) < page_size:
                break
            page += 1

        return results

    def _search_booru_org_html(self, tags: list[str], limit: int) -> list[RemotePost]:
        response = self.session.get(
            self.preset.site_url.rstrip("/") + "/index.php",
            params={"page": "post", "s": "list", "tags": " ".join(tags)},
            headers={"Accept": "text/html,application/xhtml+xml"},
            timeout=30,
        )
        response.raise_for_status()
        listing = self._extract_booru_org_listing(response.text)
        results: list[RemotePost] = []
        for post_id, href, tag_list in listing[:limit]:
            detail = self.session.get(
                urljoin(self.preset.site_url.rstrip("/") + "/", href.lstrip("/")),
                headers={"Accept": "text/html,application/xhtml+xml"},
                timeout=30,
            )
            detail.raise_for_status()
            file_url = self._extract_booru_org_file_url(detail.text)
            if not file_url:
                continue
            results.append(
                RemotePost(
                    board=self.preset.name,
                    post_id=post_id,
                    file_url=file_url,
                    filename=self.filename_from_url(file_url, post_id),
                    tags=tag_list,
                    source_url=urljoin(self.preset.site_url.rstrip("/") + "/", href.lstrip("/")),
                )
            )
        return results

    def _search_rule34_html(self, tags: list[str], limit: int) -> list[RemotePost]:
        response = self.session.get(
            self.preset.site_url.rstrip("/") + "/index.php",
            params={"page": "post", "s": "list", "tags": " ".join(tags)},
            headers={"Accept": "text/html,application/xhtml+xml"},
            timeout=30,
        )
        response.raise_for_status()
        post_links = self._extract_rule34_post_links(response.text)
        results: list[RemotePost] = []
        for post_id, source_url in post_links[:limit]:
            detail = self._get_rule34_detail(source_url)
            file_url = self._extract_rule34_file_url(detail.text)
            if not file_url:
                continue
            tags = self._extract_rule34_tags(detail.text)
            results.append(
                RemotePost(
                    board=self.preset.name,
                    post_id=post_id,
                    file_url=file_url,
                    filename=self.filename_from_url(file_url, post_id),
                    tags=tags,
                    source_url=urljoin(self.preset.site_url.rstrip("/") + "/", source_url.lstrip("/")),
                )
            )
        return results

    def _get_rule34_detail(self, source_url: str):
        target_url = urljoin(self.preset.site_url.rstrip("/") + "/", source_url.lstrip("/"))
        backoff = 1.0
        last_response = None
        for _ in range(4):
            response = self.session.get(
                target_url,
                headers={"Accept": "text/html,application/xhtml+xml"},
                timeout=30,
            )
            last_response = response
            if response.status_code != 429:
                response.raise_for_status()
                return response
            time.sleep(backoff)
            backoff *= 2
        assert last_response is not None
        last_response.raise_for_status()
        return last_response

    @staticmethod
    def _extract_posts(payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if "post" in payload and isinstance(payload["post"], list):
                return payload["post"]
            if "post" in payload and isinstance(payload["post"], dict):
                return [payload["post"]]
        return []

    @staticmethod
    def _extract_rule34_post_links(payload: str) -> list[tuple[str, str]]:
        links = re.findall(
            r'href="([^"]*index\.php\?page=post&s=view&id=(\d+)[^"]*)"',
            payload,
            flags=re.IGNORECASE,
        )
        results: list[tuple[str, str]] = []
        seen: set[str] = set()
        for href, post_id in links:
            if post_id in seen:
                continue
            seen.add(post_id)
            results.append((post_id, html.unescape(href)))
        return results

    @staticmethod
    def _extract_rule34_file_url(payload: str) -> str | None:
        matches = re.findall(
            r'https?://[^"\']+\.(?:jpg|jpeg|png|gif|webm|mp4)',
            payload,
            flags=re.IGNORECASE,
        )
        for match in matches:
            lowered = match.lower()
            if "/images/" in lowered or "ws-cdn-video.rule34.xxx" in lowered:
                return html.unescape(match)
        for match in re.findall(r'/images/[^"\']+', payload, flags=re.IGNORECASE):
            return "https://rule34.xxx" + html.unescape(match.split("?", 1)[0])
        return None

    @staticmethod
    def _extract_rule34_tags(payload: str) -> list[str]:
        tags = re.findall(
            r'/index\.php\?page=post&s=list&tags=([^"&]+)',
            payload,
            flags=re.IGNORECASE,
        )
        decoded = [html.unescape(tag.replace("+", " ")) for tag in tags]
        return BaseAdapter.dedupe_tags(decoded)

    @staticmethod
    def _extract_booru_org_listing(payload: str) -> list[tuple[str, str, list[str]]]:
        matches = re.findall(
            r'<a id="p(\d+)" href="([^"]+)"><img[^>]+title="([^"]+)"',
            payload,
            flags=re.IGNORECASE,
        )
        results: list[tuple[str, str, list[str]]] = []
        for post_id, href, title in matches:
            title = html.unescape(title).strip()
            title = title.split("score:", 1)[0].strip()
            title = title.split("rating:", 1)[0].strip()
            tag_list = BaseAdapter.dedupe_tags(title.split())
            results.append((post_id, html.unescape(href.replace("&amp;", "&")), tag_list))
        return results

    @staticmethod
    def _extract_booru_org_file_url(payload: str) -> str | None:
        matches = re.findall(
            r'https?://[^"\']+\.(?:jpg|jpeg|png|gif|webm|mp4)',
            payload,
            flags=re.IGNORECASE,
        )
        for match in matches:
            lowered = match.lower()
            if "img.booru.org" in lowered or "/images/" in lowered:
                return html.unescape(match)
        for match in re.findall(r'/images/[^"\']+', payload, flags=re.IGNORECASE):
            return html.unescape(match.split("?", 1)[0])
        return None
