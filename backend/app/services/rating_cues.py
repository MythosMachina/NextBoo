from app.core.constants import Rating
from app.models.user import User
from app.schemas.image import ImageDetail
from app.services.visibility import is_staff


EXPLICIT_CUE_TAGS = {
    "sex",
    "cum",
    "cum_in_pussy",
    "cum_overflow",
    "penis",
    "vaginal",
    "pussy",
    "ejaculation",
    "fellatio",
    "anal",
    "handjob",
    "cunnilingus",
    "paizuri",
}

QUESTIONABLE_CUE_TAGS = {
    "nude",
    "completely_nude",
    "nipples",
    "uncensored",
    "topless",
    "bottomless",
    "bare_pussy",
    "pubic_hair",
    "cameltoe",
    "areola_slip",
    "sideboob",
    "underboob",
    "cleft_of_venus",
}


def apply_staff_rating_cues(detail: ImageDetail, current_user: User | None) -> None:
    if not current_user or not is_staff(current_user):
        return

    if detail.rating == Rating.EXPLICIT:
        cue_tags = EXPLICIT_CUE_TAGS
        cue_value = "explicit"
    elif detail.rating == Rating.QUESTIONABLE:
        cue_tags = QUESTIONABLE_CUE_TAGS
        cue_value = "questionable"
    else:
        return

    for item in detail.tags:
        if item.tag.name_normalized in cue_tags:
            item.rating_cue = cue_value
