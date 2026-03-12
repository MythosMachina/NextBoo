from datetime import datetime, timezone
from typing import Annotated

from app.api.deps import DbSession, get_current_user, require_roles
from app.core.constants import UploadRequestStatus, UserRole
from app.models.upload_request import UploadPermissionRequest
from app.models.user import User
from app.schemas.upload_request import (
    UploadRequestCreate,
    UploadRequestEnvelope,
    UploadRequestRead,
    UploadRequestReview,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import aliased


router = APIRouter(prefix="/upload-requests")


def build_request_read(request: UploadPermissionRequest, username: str, reviewed_by_username: str | None) -> UploadRequestRead:
    return UploadRequestRead(
        id=request.id,
        username=username,
        user_id=request.user_id,
        content_focus=request.content_focus,
        reason=request.reason,
        status=request.status,
        review_note=request.review_note,
        reviewed_by_username=reviewed_by_username,
        created_at=request.created_at,
        reviewed_at=request.reviewed_at,
    )


@router.get("/me", response_model=UploadRequestEnvelope)
def get_my_requests(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> UploadRequestEnvelope:
    reviewer = aliased(User)
    rows = (
        db.query(UploadPermissionRequest, reviewer.username)
        .outerjoin(reviewer, reviewer.id == UploadPermissionRequest.reviewed_by_user_id)
        .filter(UploadPermissionRequest.user_id == current_user.id)
        .order_by(UploadPermissionRequest.created_at.desc())
        .all()
    )
    return UploadRequestEnvelope(
        data=[build_request_read(request, current_user.username, reviewed_by_username) for request, reviewed_by_username in rows],
        meta={"count": len(rows)},
    )


@router.post("/me", response_model=UploadRequestEnvelope, status_code=status.HTTP_201_CREATED)
def create_my_request(
    payload: UploadRequestCreate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> UploadRequestEnvelope:
    if current_user.role in {UserRole.ADMIN, UserRole.MODERATOR} or current_user.can_upload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload access already granted")
    existing = (
        db.query(UploadPermissionRequest)
        .filter(UploadPermissionRequest.user_id == current_user.id)
        .filter(UploadPermissionRequest.status == UploadRequestStatus.PENDING)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A pending request already exists")

    request = UploadPermissionRequest(
        user_id=current_user.id,
        content_focus=payload.content_focus.strip(),
        reason=payload.reason.strip(),
        status=UploadRequestStatus.PENDING,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return UploadRequestEnvelope(
        data=[build_request_read(request, current_user.username, None)],
        meta={"count": 1},
    )


@router.get("", response_model=UploadRequestEnvelope)
def list_requests(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    status_filter: UploadRequestStatus = Query(default=UploadRequestStatus.PENDING, alias="status"),
) -> UploadRequestEnvelope:
    requester = aliased(User)
    reviewer = aliased(User)
    rows = (
        db.query(UploadPermissionRequest, requester.username, reviewer.username)
        .join(requester, requester.id == UploadPermissionRequest.user_id)
        .outerjoin(reviewer, reviewer.id == UploadPermissionRequest.reviewed_by_user_id)
        .filter(UploadPermissionRequest.status == status_filter)
        .order_by(UploadPermissionRequest.created_at.asc())
        .all()
    )
    return UploadRequestEnvelope(
        data=[build_request_read(request, username, reviewed_by_username) for request, username, reviewed_by_username in rows],
        meta={"count": len(rows), "status": status_filter.value},
    )


@router.patch("/{request_id}", response_model=UploadRequestEnvelope)
def review_request(
    request_id: int,
    payload: UploadRequestReview,
    db: DbSession,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UploadRequestEnvelope:
    request = db.get(UploadPermissionRequest, request_id)
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")
    if request.status != UploadRequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request already processed")
    if payload.status not in {UploadRequestStatus.APPROVED, UploadRequestStatus.REJECTED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Processed requests must be approved or rejected")

    request.status = payload.status
    request.review_note = payload.review_note.strip() if payload.review_note else None
    request.reviewed_by_user_id = current_user.id
    request.reviewed_at = datetime.now(timezone.utc)

    target_user = db.get(User, request.user_id)
    if payload.status == UploadRequestStatus.APPROVED and target_user:
        target_user.can_upload = True
        db.add(target_user)

    db.add(request)
    db.commit()
    db.refresh(request)
    return UploadRequestEnvelope(
        data=[build_request_read(request, target_user.username if target_user else "unknown", current_user.username)],
        meta={"count": 1},
    )
