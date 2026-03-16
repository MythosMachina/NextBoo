from dataclasses import dataclass, field

from app.core.constants import Rating


RATING_ALIASES = {
    "safe": Rating.GENERAL,
    "general": Rating.GENERAL,
    "g": Rating.GENERAL,
    "sensitive": Rating.SENSITIVE,
    "s": Rating.SENSITIVE,
    "questionable": Rating.QUESTIONABLE,
    "q": Rating.QUESTIONABLE,
    "explicit": Rating.EXPLICIT,
    "x": Rating.EXPLICIT,
    "e": Rating.EXPLICIT,
}


@dataclass
class ParsedSearchQuery:
    include_tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    rating: Rating | None = None
    sort: str = "recent"


MEDIA_TYPE_ALIASES = {
    "image": "image",
    "animated": "animated",
    "video": "video",
}


def normalize_tag_token(value: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized


def parse_rating_filter(value: str | None) -> Rating | None:
    if not value:
        return None
    return RATING_ALIASES.get(value.strip().lower())


def parse_media_type_filter(value: str | None) -> str | None:
    if not value:
        return None
    return MEDIA_TYPE_ALIASES.get(value.strip().lower())


def parse_search_query(query: str) -> ParsedSearchQuery:
    parsed = ParsedSearchQuery()
    for raw_token in query.split():
        token = raw_token.strip()
        if not token:
            continue
        if token.startswith("rating:"):
            rating_value = token.split(":", 1)[1]
            if rating_value in RATING_ALIASES:
                parsed.rating = RATING_ALIASES[rating_value]
            continue
        if token.startswith("sort:"):
            parsed.sort = token.split(":", 1)[1]
            continue
        if token.startswith("-"):
            parsed.exclude_tags.append(normalize_tag_token(token[1:]))
            continue
        parsed.include_tags.append(normalize_tag_token(token))
    return parsed
