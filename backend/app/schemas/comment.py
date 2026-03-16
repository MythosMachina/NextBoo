from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ImageCommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    parent_comment_id: int | None = None


class ImageCommentUpdate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    moderation_reason: str | None = None


class CommentVoteCreate(BaseModel):
    value: int = Field(..., ge=-1, le=1)


class ImageCommentAuthor(BaseModel):
    id: int
    username: str


class ImageCommentRead(BaseModel):
    id: int
    body: str
    is_edited: bool
    is_flagged: bool
    score: int = 0
    current_user_vote: int | None = None
    created_at: datetime
    updated_at: datetime
    author: ImageCommentAuthor
    replies: list["ImageCommentRead"] = []
