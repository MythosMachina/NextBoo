from app.models.user import User


def normalize_tag_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        candidate = "_".join(raw_value.strip().lower().split())
        while "__" in candidate:
            candidate = candidate.replace("__", "_")
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def parse_user_tag_blacklist(user: User | None) -> list[str]:
    if not user or not user.tag_blacklist:
        return []
    return normalize_tag_list(user.tag_blacklist.splitlines())


def serialize_tag_blacklist(values: list[str]) -> str:
    return "\n".join(normalize_tag_list(values))
