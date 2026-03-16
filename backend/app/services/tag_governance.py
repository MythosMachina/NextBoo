import re

from app.core.constants import TagCategory
from app.models.tag import Tag


NAME_PATTERN_RE = re.compile(r"^[a-z0-9][a-z0-9_]*_\([a-z0-9][a-z0-9_ ]*\)$")


def is_name_pattern_tag(tag: Tag) -> bool:
    if tag.category not in {TagCategory.CHARACTER, TagCategory.COPYRIGHT, TagCategory.ARTIST, TagCategory.GENERAL}:
        return False
    return bool(NAME_PATTERN_RE.match(tag.name_normalized))
