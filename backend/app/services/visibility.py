from app.core.constants import Rating, UserRole, VisibilityStatus
from app.models.image import Image
from app.models.image import ImageTag
from app.models.moderation import ImageModeration
from app.models.tag import Tag
from app.models.user import User
from app.services.user_preferences import parse_user_tag_blacklist
from sqlalchemy import or_


def is_staff(user: User | None) -> bool:
    return bool(user and user.role in {UserRole.ADMIN, UserRole.MODERATOR})


def is_owner(user: User | None, image: Image) -> bool:
    return bool(user and image.uploaded_by_user_id and user.id == image.uploaded_by_user_id)


def resolve_visibility_status(image: Image) -> VisibilityStatus:
    return image.moderation.visibility_status if image.moderation else VisibilityStatus.VISIBLE


def apply_public_image_visibility(query, current_user: User | None):
    query = query.outerjoin(ImageModeration, ImageModeration.image_id == Image.id)
    if not is_staff(current_user):
        query = query.filter(
            or_(
                ImageModeration.image_id.is_(None),
                ImageModeration.visibility_status == VisibilityStatus.VISIBLE,
            )
        )
    if not is_staff(current_user):
        if current_user is None:
            query = query.filter(Image.rating == Rating.GENERAL)
        elif not current_user.can_view_questionable:
            query = query.filter(Image.rating.in_((Rating.GENERAL, Rating.SENSITIVE)))
    if not (current_user and (current_user.can_view_explicit or is_staff(current_user))):
        query = query.filter(Image.rating != Rating.EXPLICIT)
    blacklist = parse_user_tag_blacklist(current_user)
    if blacklist and not is_staff(current_user):
        query = query.filter(
            ~Image.tags.any(
                ImageTag.tag.has(Tag.name_normalized.in_(blacklist))
            )
        )
    return query


def image_has_blacklisted_tags(image: Image, current_user: User | None) -> bool:
    if is_staff(current_user):
        return False
    blacklist = set(parse_user_tag_blacklist(current_user))
    if not blacklist:
        return False
    return any(item.tag.name_normalized in blacklist for item in image.tags if item.tag)
