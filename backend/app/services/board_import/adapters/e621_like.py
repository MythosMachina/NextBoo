from __future__ import annotations

from app.services.board_import.adapters.common import BaseAdapter
from app.services.board_import.models import RemotePost


class E621LikeAdapter(BaseAdapter):
    def search_posts(self, tags: list[str], limit: int) -> list[RemotePost]:
        remaining = limit
        page = 1
        results: list[RemotePost] = []
        effective_tags = list(tags)
        if self.preset.name.upper() == "E926" and not any(tag.startswith("rating:") for tag in effective_tags):
            effective_tags.append("rating:s")
        tag_query = " ".join(effective_tags)

        while remaining > 0:
            page_size = min(320, remaining)
            response = self.session.get(
                self.preset.search_url,
                params={"tags": tag_query, "limit": page_size, "page": page},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            posts = payload.get("posts", [])
            if not posts:
                break

            for post in posts:
                file_url = (post.get("file") or {}).get("url")
                if not file_url:
                    continue

                post_id = str(post["id"])
                source_url = f"{self.preset.site_url.rstrip('/')}/posts/{post_id}"
                filename = self.filename_from_url(file_url, post_id)
                tags_flat = self._flatten_tags(post.get("tags") or {})

                results.append(
                    RemotePost(
                        board=self.preset.name,
                        post_id=post_id,
                        file_url=file_url,
                        filename=filename,
                        mime_type=self.mime_type_from_filename(filename),
                        tags=tags_flat,
                        source_url=source_url,
                        md5=(post.get("file") or {}).get("md5"),
                    )
                )

                remaining -= 1
                if remaining <= 0:
                    break

            if len(posts) < page_size:
                break

            page += 1

        return results

    def _flatten_tags(self, tags_payload: dict[str, list[str]]) -> list[str]:
        ordered_buckets = (
            "artist",
            "character",
            "copyright",
            "species",
            "meta",
            "lore",
            "general",
        )
        values: list[str] = []
        for bucket in ordered_buckets:
            values.extend(tags_payload.get(bucket, []))
        return self.dedupe_tags(values)
