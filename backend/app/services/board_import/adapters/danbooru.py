from __future__ import annotations

from app.services.board_import.adapters.common import BaseAdapter
from app.services.board_import.models import RemotePost


class DanbooruAdapter(BaseAdapter):
    def search_posts(self, tags: list[str], limit: int) -> list[RemotePost]:
        remaining = limit
        page = 1
        results: list[RemotePost] = []
        tag_query = " ".join(tags)

        while remaining > 0:
            page_size = min(100, remaining)
            response = self.session.get(
                self.preset.search_url,
                params={"tags": tag_query, "limit": page_size, "page": page},
                timeout=30,
            )
            response.raise_for_status()
            posts = response.json()
            if not posts:
                break

            for post in posts:
                file_url = post.get("file_url") or post.get("large_file_url")
                if not file_url:
                    continue
                post_id = str(post["id"])
                tags_flat = self.dedupe_tags(
                    (
                        (post.get("tag_string_artist") or "").split()
                        + (post.get("tag_string_character") or "").split()
                        + (post.get("tag_string_copyright") or "").split()
                        + (post.get("tag_string_meta") or "").split()
                        + (post.get("tag_string_general") or "").split()
                    )
                )
                results.append(
                    RemotePost(
                        board=self.preset.name,
                        post_id=post_id,
                        file_url=file_url,
                        filename=self.filename_from_url(file_url, post_id),
                        tags=tags_flat,
                        source_url=f"{self.preset.site_url.rstrip('/')}/posts/{post_id}",
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
