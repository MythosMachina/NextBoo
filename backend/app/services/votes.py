from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.vote import ImageVote, UserVoteThrottle
from sqlalchemy import func
from sqlalchemy.orm import Session


VOTE_WINDOW_SECONDS = 600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_vote_score(db: Session, image_id: str) -> int:
    score = db.query(func.coalesce(func.sum(ImageVote.value), 0)).filter(ImageVote.image_id == image_id).scalar()
    return int(score or 0)


def get_user_vote(db: Session, image_id: str, user_id: int | None) -> int | None:
    if user_id is None:
        return None
    vote = db.get(ImageVote, {"image_id": image_id, "user_id": user_id})
    return int(vote.value) if vote else None


def get_or_create_vote_throttle(db: Session, user_id: int) -> UserVoteThrottle:
    throttle = db.get(UserVoteThrottle, user_id)
    if throttle is None:
        throttle = UserVoteThrottle(user_id=user_id, actions_in_window=0)
        db.add(throttle)
        db.flush()
    return throttle


def get_vote_throttle(db: Session, user_id: int) -> UserVoteThrottle | None:
    return db.get(UserVoteThrottle, user_id)


def current_cooldown_remaining(throttle: UserVoteThrottle, now: datetime | None = None) -> int:
    now = now or _now()
    if not throttle.window_started_at or (now - throttle.window_started_at).total_seconds() >= VOTE_WINDOW_SECONDS:
        return 0
    if not throttle.cooldown_until or throttle.cooldown_until <= now:
        return 0
    return max(int((throttle.cooldown_until - now).total_seconds()), 0)


def register_vote_action(db: Session, user_id: int) -> int:
    now = _now()
    throttle = get_or_create_vote_throttle(db, user_id)
    if not throttle.window_started_at or (now - throttle.window_started_at).total_seconds() >= VOTE_WINDOW_SECONDS:
        throttle.window_started_at = now
        throttle.actions_in_window = 1
    else:
        throttle.actions_in_window = int(throttle.actions_in_window or 0) + 1
    cooldown_seconds = 2 ** throttle.actions_in_window
    throttle.cooldown_until = now + timedelta(seconds=cooldown_seconds)
    db.add(throttle)
    return cooldown_seconds


def upsert_image_vote(db: Session, image_id: str, user_id: int, value: int) -> int:
    now = _now()
    vote = db.get(ImageVote, {"image_id": image_id, "user_id": user_id})
    if vote is None:
        vote = ImageVote(image_id=image_id, user_id=user_id, value=value, created_at=now, updated_at=now)
        db.add(vote)
        db.flush()
        return value
    delta = value - int(vote.value)
    vote.value = value
    vote.updated_at = now
    db.add(vote)
    return delta
