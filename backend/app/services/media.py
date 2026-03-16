from app.core.constants import VariantType
from app.models.image import Image


def build_media_url(relative_path: str) -> str:
    return f"/media/{relative_path.lstrip('/')}"


def thumb_url_for_image(image: Image) -> str | None:
    for variant in image.variants:
        if variant.variant_type == VariantType.THUMB:
            return build_media_url(variant.relative_path)
    return None


def preview_url_for_image(image: Image) -> str | None:
    for variant in image.variants:
        if variant.variant_type == VariantType.PREVIEW:
            return build_media_url(variant.relative_path)
    return None
