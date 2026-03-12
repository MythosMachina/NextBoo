from app.core.constants import SYSTEM_TAGS
from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.models.image import ImageTag
from app.models.tag import Tag


def _orphan_tag_ids_query(tag_ids: set[int] | None = None):
    query = (
        select(Tag.id)
        .where(~Tag.name_normalized.in_(SYSTEM_TAGS))
        .where(~exists(select(1).where(ImageTag.tag_id == Tag.id)))
    )
    if tag_ids:
        query = query.where(Tag.id.in_(tag_ids))
    return query


def prune_orphan_tags(db: Session, tag_ids: set[int] | None = None) -> int:
    orphan_tag_ids = list(db.execute(_orphan_tag_ids_query(tag_ids)).scalars())
    if not orphan_tag_ids:
        return 0

    db.execute(delete(Tag).where(Tag.id.in_(orphan_tag_ids)))
    return len(orphan_tag_ids)
