from app.core.constants import Rating, TagCategory
from pydantic import BaseModel, Field


class TagRatingRuleUpsert(BaseModel):
    tag_name: str = Field(min_length=1, max_length=255)
    target_rating: Rating
    boost: float = Field(default=0.2, ge=0.0, le=1.0)
    is_enabled: bool = True


class TagRatingRuleRead(BaseModel):
    id: int
    tag_id: int
    tag_name: str
    display_name: str
    tag_category: TagCategory
    target_rating: Rating
    boost: float
    is_enabled: bool


class TagRatingRuleEnvelope(BaseModel):
    data: list[TagRatingRuleRead]
    meta: dict[str, int | str] = {}
