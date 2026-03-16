from pydantic import BaseModel, Field


class ImageVoteCreate(BaseModel):
    value: int = Field(..., ge=-1, le=1)


class ImageVoteRead(BaseModel):
    image_id: str
    vote_score: int
    current_user_vote: int | None
    vote_cooldown_remaining_seconds: int
