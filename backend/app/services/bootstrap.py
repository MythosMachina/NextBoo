from app.core.constants import SYSTEM_TAGS, TagCategory
from app.models.tag import Tag
from sqlalchemy.orm import Session


def ensure_system_tags(db: Session) -> None:
    existing = {
        tag.name_normalized: tag
        for tag in db.query(Tag).filter(Tag.name_normalized.in_(SYSTEM_TAGS)).all()
    }
    changed = False

    for tag_name in sorted(SYSTEM_TAGS):
        tag = existing.get(tag_name)
        if tag:
            if tag.display_name != tag_name or tag.category != TagCategory.META or not tag.is_active:
                tag.display_name = tag_name
                tag.category = TagCategory.META
                tag.is_active = True
                db.add(tag)
                changed = True
            continue

        db.add(
            Tag(
                name_normalized=tag_name,
                display_name=tag_name,
                category=TagCategory.META,
                is_active=True,
                is_locked=False,
            )
        )
        changed = True

    if changed:
        db.commit()
