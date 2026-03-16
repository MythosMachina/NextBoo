from datetime import datetime, timezone
from typing import Annotated

from app.api.deps import DbSession, RedisClient, get_current_user, require_roles
from app.core.constants import Rating, ReportStatus, UserRole, VisibilityStatus
from app.models.image import Image
from app.models.comment import CommentVote, ImageComment
from app.models.moderation import ImageModeration, ImageReport, NearDuplicateReview
from app.models.tag import Tag, TagRatingRule
from app.models.user import User
from app.schemas.moderation import (
    ModerationCommentRead,
    ModerationCommentsEnvelope,
    ModerationImageRead,
    ModerationImagesEnvelope,
    ModerationNearDuplicateRead,
    ModerationNearDuplicatesEnvelope,
    ModerationReportRead,
    ModerationReportsEnvelope,
    ReportReviewUpdate,
)
from app.schemas.tag_rating_rule import TagRatingRuleEnvelope, TagRatingRuleUpsert
from app.services.rating_rules import get_or_create_rule_tag, reclassify_all_images_from_rules
from app.services.rate_limits import enforce_rate_limit
from app.services.visibility import resolve_visibility_status
from fastapi import APIRouter, Depends, Query, HTTPException, Request, status
from sqlalchemy import desc, func
from sqlalchemy.orm import aliased


router = APIRouter(prefix="/moderation")


@router.get("/rating-rules", response_model=TagRatingRuleEnvelope)
def list_rating_rules(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> TagRatingRuleEnvelope:
    rows = (
        db.query(TagRatingRule, Tag)
        .join(Tag, Tag.id == TagRatingRule.tag_id)
        .order_by(TagRatingRule.target_rating.asc(), Tag.name_normalized.asc())
        .all()
    )
    return TagRatingRuleEnvelope(
        data=[
            {
                "id": rule.id,
                "tag_id": tag.id,
                "tag_name": tag.name_normalized,
                "display_name": tag.display_name,
                "tag_category": tag.category,
                "target_rating": Rating(rule.target_rating),
                "boost": float(rule.boost),
                "is_enabled": rule.is_enabled,
            }
            for rule, tag in rows
        ],
        meta={"count": len(rows)},
    )


@router.put("/rating-rules")
def upsert_rating_rule(
    payload: TagRatingRuleUpsert,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    tag = get_or_create_rule_tag(db, payload.tag_name)
    rule = db.query(TagRatingRule).filter(TagRatingRule.tag_id == tag.id).first()
    if rule is None:
        rule = TagRatingRule(tag_id=tag.id)
    rule.target_rating = payload.target_rating.value
    rule.boost = payload.boost
    rule.is_enabled = payload.is_enabled
    db.add(rule)
    db.commit()
    return {"data": {"status": "saved", "tag_name": tag.name_normalized}, "meta": {}}


@router.delete("/rating-rules/{rule_id}")
def delete_rating_rule(
    rule_id: int,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    rule = db.get(TagRatingRule, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rating rule not found")
    db.delete(rule)
    db.commit()
    return {"data": {"status": "deleted"}, "meta": {}}


@router.post("/rating-rules/reclassify")
def reclassify_existing_ratings(
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    changed = reclassify_all_images_from_rules(db)
    db.commit()
    return {"data": {"status": "reclassified", "changed_images": changed}, "meta": {}}


@router.get("/reports", response_model=ModerationReportsEnvelope)
def list_reports(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    image_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
) -> ModerationReportsEnvelope:
    reporter = aliased(User)
    reviewer = aliased(User)
    query = (
        db.query(ImageReport, Image, reporter.username, reviewer.username)
        .join(Image, Image.id == ImageReport.image_id)
        .outerjoin(reporter, reporter.id == ImageReport.reported_by_user_id)
        .outerjoin(reviewer, reviewer.id == ImageReport.reviewed_by_user_id)
        .outerjoin(ImageModeration, ImageModeration.image_id == Image.id)
        .order_by(desc(ImageReport.created_at))
    )
    if report_status:
        query = query.filter(ImageReport.status == report_status)
    elif image_id is None:
        query = query.filter(ImageReport.status.in_([ReportStatus.OPEN, ReportStatus.IN_REVIEW]))
    if image_id:
        query = query.filter(ImageReport.image_id == image_id)

    rows = query.limit(limit).all()
    data = [
        ModerationReportRead(
            id=report.id,
            image_id=image.id,
            image_uuid_short=image.uuid_short,
            image_rating=image.rating,
            image_visibility_status=resolve_visibility_status(image),
            reported_by_username=reported_by_username,
            reason=report.reason,
            message=report.message,
            status=report.status,
            review_note=report.review_note,
            reviewed_by_username=reviewed_by_username,
            created_at=report.created_at,
            reviewed_at=report.reviewed_at,
        )
        for report, image, reported_by_username, reviewed_by_username in rows
    ]
    return ModerationReportsEnvelope(
        data=data,
        meta={
            "count": len(data),
            "status": report_status.value if report_status else "all",
            "image_id": image_id,
        },
    )


@router.patch("/reports/{report_id}")
def review_report(
    report_id: int,
    payload: ReportReviewUpdate,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if current_user.role not in {UserRole.ADMIN, UserRole.MODERATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    report = db.get(ImageReport, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    report.status = payload.status
    report.review_note = payload.review_note.strip() if payload.review_note else None
    report.reviewed_by_user_id = current_user.id
    report.reviewed_at = datetime.now(timezone.utc)
    db.add(report)
    db.commit()
    return {"data": {"status": report.status.value}, "meta": {}}


@router.get("/images", response_model=ModerationImagesEnvelope)
def list_moderation_images(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    visibility: str = Query(default="needs_review"),
    limit: int = Query(default=100, ge=1, le=200),
) -> ModerationImagesEnvelope:
    open_reports_subquery = (
        db.query(ImageReport.image_id, func.count(ImageReport.id).label("report_count_open"))
        .filter(ImageReport.status.in_([ReportStatus.OPEN, ReportStatus.IN_REVIEW]))
        .group_by(ImageReport.image_id)
        .subquery()
    )

    query = (
        db.query(
            Image,
            ImageModeration.visibility_status,
            User.username,
            func.coalesce(open_reports_subquery.c.report_count_open, 0),
        )
        .outerjoin(ImageModeration, ImageModeration.image_id == Image.id)
        .outerjoin(User, User.id == Image.uploaded_by_user_id)
        .outerjoin(open_reports_subquery, open_reports_subquery.c.image_id == Image.id)
        .order_by(desc(Image.created_at))
    )

    if visibility == "needs_review":
        query = query.filter(
            (
                (ImageModeration.visibility_status == VisibilityStatus.HIDDEN)
                | (func.coalesce(open_reports_subquery.c.report_count_open, 0) > 0)
            )
        )
        query = query.filter(
            (ImageModeration.visibility_status.is_(None)) | (ImageModeration.visibility_status != VisibilityStatus.DELETED)
        )
    elif visibility in {"visible", "hidden", "deleted"}:
        query = query.filter(ImageModeration.visibility_status == visibility)

    rows = query.limit(limit).all()
    data = [
        ModerationImageRead(
            id=image.id,
            uuid_short=image.uuid_short,
            original_filename=image.original_filename,
            rating=image.rating,
            visibility_status=visibility_status or resolve_visibility_status(image),
            uploaded_by_username=uploaded_by_username,
            report_count_open=report_count_open,
            created_at=image.created_at,
        )
        for image, visibility_status, uploaded_by_username, report_count_open in rows
    ]
    return ModerationImagesEnvelope(data=data, meta={"count": len(data), "visibility": visibility})


@router.get("/comments", response_model=ModerationCommentsEnvelope)
def list_flagged_comments(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    flagged_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=200),
) -> ModerationCommentsEnvelope:
    author = aliased(User)
    score_subquery = (
        db.query(CommentVote.comment_id, func.coalesce(func.sum(CommentVote.value), 0).label("score"))
        .group_by(CommentVote.comment_id)
        .subquery()
    )

    query = (
        db.query(
            ImageComment,
            Image,
            author.username,
            func.coalesce(score_subquery.c.score, 0),
        )
        .join(Image, Image.id == ImageComment.image_id)
        .outerjoin(author, author.id == ImageComment.user_id)
        .outerjoin(score_subquery, score_subquery.c.comment_id == ImageComment.id)
        .order_by(desc(ImageComment.updated_at))
    )
    if flagged_only:
        query = query.filter(ImageComment.is_flagged.is_(True))

    rows = query.limit(limit).all()
    data = [
        ModerationCommentRead(
            id=comment.id,
            image_id=image.id,
            image_uuid_short=image.uuid_short,
            image_rating=image.rating,
            body=comment.body,
            score=int(score or 0),
            is_flagged=comment.is_flagged,
            author_username=author_username,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
        for comment, image, author_username, score in rows
    ]
    return ModerationCommentsEnvelope(data=data, meta={"count": len(data), "flagged_only": "true" if flagged_only else "false"})


@router.patch("/comments/{comment_id}/clear-flag")
def clear_comment_flag(
    comment_id: int,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    comment = db.get(ImageComment, comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    comment.is_flagged = False
    db.add(comment)
    db.commit()
    return {"data": {"status": "cleared", "comment_id": comment.id}, "meta": {}}


@router.get("/near-duplicates", response_model=ModerationNearDuplicatesEnvelope)
def list_near_duplicates(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    status_filter: str = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=200),
) -> ModerationNearDuplicatesEnvelope:
    left_image = aliased(Image)
    right_image = aliased(Image)
    query = (
        db.query(NearDuplicateReview, left_image, right_image)
        .join(left_image, left_image.id == NearDuplicateReview.image_id)
        .join(right_image, right_image.id == NearDuplicateReview.similar_image_id)
        .order_by(desc(NearDuplicateReview.created_at))
    )
    if status_filter != "all":
        query = query.filter(NearDuplicateReview.status == status_filter)

    rows = query.limit(limit).all()
    return ModerationNearDuplicatesEnvelope(
        data=[
            ModerationNearDuplicateRead(
                id=review.id,
                image_id=review.image_id,
                similar_image_id=review.similar_image_id,
                image_uuid_short=image.uuid_short,
                similar_image_uuid_short=similar_image.uuid_short,
                hamming_distance=review.hamming_distance,
                status=review.status,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            for review, image, similar_image in rows
        ],
        meta={"count": len(rows), "status": status_filter},
    )


@router.patch("/near-duplicates/{review_id}")
def review_near_duplicate(
    review_id: int,
    action: str,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    review = db.get(NearDuplicateReview, review_id)
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Near duplicate review not found")
    normalized_action = action.strip().lower()
    if normalized_action not in {"dismissed", "confirmed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")
    review.status = normalized_action
    review.reviewed_by_user_id = current_user.id
    review.reviewed_at = datetime.now(timezone.utc)
    db.add(review)
    db.commit()
    return {"data": {"status": review.status, "review_id": review.id}, "meta": {}}
