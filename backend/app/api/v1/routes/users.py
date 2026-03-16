from pathlib import Path
from typing import Annotated

from app.api.deps import DbSession, get_current_user, get_current_user_raw, get_optional_current_user, require_roles
from app.core.constants import ProcessingStatus, Rating, UserRole
from app.core.security import hash_password, verify_password
from app.models.backup_export import BackupExport
from app.models.image import Image
from app.models.user import User
from app.schemas.user import (
    AdminUserBan,
    AdminUserPasswordReset,
    BackupDownloadsEnvelope,
    BackupExportItem,
    BackupImageItem,
    PublicUserProfileEnvelope,
    PublicUserProfileImage,
    PublicUserResponse,
    UserCreate,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserResponse,
    UserUpdate,
    UsersEnvelope,
)
from app.services.admin_users import email_is_banned, generate_temp_password
from app.services.backup_exports import EXPORT_ROOT, list_backup_exports_for_user, queue_backup_export, reactivate_tos_account
from app.services.media import build_media_url, thumb_url_for_image
from app.services.social_gate import ban_user_with_enforcement, can_manage_target, count_used_invites, count_user_strikes
from app.services.tos import get_current_tos_version, user_requires_tos_acceptance
from app.services.deletion import hard_delete_image
from app.services.storage_sanitation import sanitize_gallery_storage
from app.services.user_preferences import parse_user_tag_blacklist, serialize_tag_blacklist
from app.services.visibility import apply_public_image_visibility, resolve_visibility_status
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload


router = APIRouter(prefix="/users")


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _require_tos_backup_user(current_user: User) -> None:
    if current_user.role != UserRole.TOS_DEACTIVATED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Backup downloads are only available in Terms of Service backup-only mode")


def _build_user_response(db: Session, user: User) -> UserResponse:
    invite_slots_used = count_used_invites(db, user.id)
    strike_count = count_user_strikes(db, user.id)
    current_tos_version = get_current_tos_version(db)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        is_banned=user.is_banned,
        can_upload=user.can_upload or user.role in {UserRole.ADMIN, UserRole.MODERATOR},
        invite_quota=user.invite_quota,
        invite_slots_used=invite_slots_used,
        invite_slots_remaining=max(user.invite_quota - invite_slots_used, 0),
        invited_by_username=user.invited_by.username if user.invited_by else None,
        strike_count=strike_count,
        can_view_questionable=user.can_view_questionable,
        can_view_explicit=user.can_view_explicit,
        tag_blacklist=parse_user_tag_blacklist(user),
        requires_tos_acceptance=user_requires_tos_acceptance(db, user),
        accepted_tos_version=user.accepted_tos_version,
        current_tos_version=current_tos_version,
        tos_declined_at=user.tos_declined_at.isoformat() if user.tos_declined_at else None,
        tos_delete_after_at=user.tos_delete_after_at.isoformat() if user.tos_delete_after_at else None,
    )


@router.get("", response_model=UsersEnvelope)
def list_users(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UsersEnvelope:
    users = db.query(User).order_by(User.username.asc()).all()
    return UsersEnvelope(data=[_build_user_response(db, user) for user in users], meta={"count": len(users)})


@router.get("/profile/{username}", response_model=PublicUserProfileEnvelope)
def get_public_profile(
    username: str,
    db: DbSession,
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
    limit: int = Query(default=48, ge=1, le=100),
) -> PublicUserProfileEnvelope:
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    uploads_query = (
        db.query(Image)
        .options(selectinload(Image.variants), selectinload(Image.moderation))
        .filter(Image.uploaded_by_user_id == user.id)
        .filter(Image.processing_status == ProcessingStatus.READY)
        .order_by(Image.created_at.desc())
    )
    uploads_query = apply_public_image_visibility(uploads_query, current_user)

    uploads = uploads_query.limit(limit).all()
    upload_items: list[PublicUserProfileImage] = []
    for image in uploads:
        item = PublicUserProfileImage.model_validate(image)
        item.thumb_url = thumb_url_for_image(image)
        item.visibility_status = resolve_visibility_status(image)
        upload_items.append(item)

    return PublicUserProfileEnvelope(
        data=PublicUserResponse.model_validate(user),
        uploads=upload_items,
        meta={"count": len(upload_items), "limit": limit},
    )


@router.get("/me/uploads", response_model=PublicUserProfileEnvelope)
def get_my_uploads(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(default=100, ge=1, le=200),
) -> PublicUserProfileEnvelope:
    uploads = (
        db.query(Image)
        .options(selectinload(Image.variants), selectinload(Image.moderation))
        .filter(Image.uploaded_by_user_id == current_user.id)
        .filter(Image.processing_status == ProcessingStatus.READY)
        .order_by(Image.created_at.desc())
        .limit(limit)
        .all()
    )
    upload_items: list[PublicUserProfileImage] = []
    for image in uploads:
        item = PublicUserProfileImage.model_validate(image)
        item.thumb_url = thumb_url_for_image(image)
        item.visibility_status = resolve_visibility_status(image)
        upload_items.append(item)

    return PublicUserProfileEnvelope(
        data=PublicUserResponse.model_validate(current_user),
        uploads=upload_items,
        meta={"count": len(upload_items), "limit": limit},
    )


@router.get("/me/backup", response_model=BackupDownloadsEnvelope)
def get_my_backup_downloads(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user_raw)],
    limit: int = Query(default=500, ge=1, le=2000),
) -> BackupDownloadsEnvelope:
    _require_tos_backup_user(current_user)
    uploads = (
        db.query(Image)
        .options(selectinload(Image.variants))
        .filter(Image.uploaded_by_user_id == current_user.id)
        .filter(Image.processing_status == ProcessingStatus.READY)
        .order_by(Image.created_at.desc())
        .limit(limit)
        .all()
    )
    items: list[BackupImageItem] = []
    for image in uploads:
        original_variant = next((variant for variant in image.variants if variant.variant_type.value == "original"), None)
        items.append(
            BackupImageItem(
                id=image.id,
                uuid_short=image.uuid_short,
                original_filename=image.original_filename,
                created_at=image.created_at,
                rating=image.rating,
                original_download_url=build_media_url(original_variant.relative_path) if original_variant else None,
            )
        )
    exports = [
        BackupExportItem(
            id=export.id,
            status=export.status,
            created_at=export.created_at,
            started_at=export.started_at,
            finished_at=export.finished_at,
            file_size=export.file_size,
            item_count=export.item_count,
            current_message=export.current_message,
            error_summary=export.error_summary,
            download_url=f"/api/v1/users/me/backup/exports/{export.id}/download"
            if export.status == "done" and export.zip_relative_path
            else None,
        )
        for export in list_backup_exports_for_user(db, current_user)
    ]
    return BackupDownloadsEnvelope(
        data=items,
        exports=exports,
        meta={"count": len(items), "limit": limit, "export_count": len(exports)},
    )


@router.post("/me/backup/exports", response_model=BackupDownloadsEnvelope)
def create_my_backup_export(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user_raw)],
) -> BackupDownloadsEnvelope:
    _require_tos_backup_user(current_user)
    export, created = queue_backup_export(db, current_user)
    uploads_envelope = get_my_backup_downloads(db, current_user, limit=500)
    uploads_envelope.meta["queued_export_id"] = export.id
    uploads_envelope.meta["queued"] = 1 if created else 0
    return uploads_envelope


@router.get("/me/backup/exports/{export_id}/download")
def download_my_backup_export(
    export_id: int,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user_raw)],
):
    _require_tos_backup_user(current_user)
    export = db.get(BackupExport, export_id)
    if not export or export.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup export not found")
    if export.status != "done" or not export.zip_relative_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Backup export is not ready")
    archive_path = EXPORT_ROOT / Path(export.zip_relative_path).name
    if not archive_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup archive is missing")
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=archive_path.name,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UserResponse:
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    if email_is_banned(db, payload.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email address is banned")
    user = User(
        username=payload.username,
        email=_normalize_email(payload.email),
        password_hash=hash_password(payload.password),
        role=payload.role,
        invite_quota=50 if payload.role == UserRole.ADMIN else 2,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _build_user_response(db, user)


@router.patch("/me", response_model=UserResponse)
def update_profile_me(
    payload: UserProfileUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    if payload.can_view_questionable is not None:
        current_user.can_view_questionable = payload.can_view_questionable
    if payload.can_view_explicit is not None:
        current_user.can_view_explicit = payload.can_view_explicit
    if payload.tag_blacklist is not None:
        current_user.tag_blacklist = serialize_tag_blacklist(payload.tag_blacklist)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _build_user_response(db, current_user)


@router.patch("/me/password")
def update_password_me(
    payload: UserPasswordUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")
    current_user.password_hash = hash_password(payload.new_password)
    db.add(current_user)
    db.commit()
    return {"data": {"status": "ok"}, "meta": {}}


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: DbSession,
    current_admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UserResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account")
    if user.id == current_admin.id and payload.is_banned is True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot ban your own account")
    if payload.is_banned is True and not user.is_banned:
        ban_user_with_enforcement(db, target_user=user, actor_user=current_admin, reason="Banned from admin user edit", propagate_inviter=True)
        db.commit()
        db.refresh(user)
        return _build_user_response(db, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "email":
            value = _normalize_email(value)
            if value is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email address is required")
            if email_is_banned(db, value):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email address is banned")
        if field == "invite_quota" and value is not None and value < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite quota cannot be negative")
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _build_user_response(db, user)


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: AdminUserPasswordReset,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    new_password = payload.new_password or generate_temp_password()
    if len(new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")
    user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()
    return {"data": {"status": "ok", "temporary_password": new_password}, "meta": {}}


@router.post("/{user_id}/ban", response_model=UserResponse)
def ban_user(
    user_id: int,
    payload: AdminUserBan,
    db: DbSession,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> UserResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not can_manage_target(current_user, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot ban this account")
    ban_user_with_enforcement(db, target_user=user, actor_user=current_user, reason=payload.reason, propagate_inviter=True)
    db.commit()
    db.refresh(user)
    return _build_user_response(db, user)


@router.delete("/{user_id}")
def remove_user(
    user_id: int,
    db: DbSession,
    current_admin: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot remove your own account")
    db.delete(user)
    db.commit()
    return {"data": {"status": "removed"}, "meta": {}}


@router.post("/{user_id}/purge-content")
def purge_user_content(
    user_id: int,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    images = (
        db.query(Image)
        .options(
            selectinload(Image.variants),
            selectinload(Image.tags),
            selectinload(Image.moderation),
            selectinload(Image.reports),
        )
        .filter(Image.uploaded_by_user_id == user.id)
        .all()
    )

    removed = 0
    for image in images:
        hard_delete_image(db, image)
        removed += 1

    sanitize_gallery_storage(db)
    db.commit()
    return {"data": {"status": "purged", "removed_images": removed}, "meta": {}}


@router.post("/{user_id}/reactivate-tos", response_model=UserResponse)
def reactivate_tos_user(
    user_id: int,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UserResponse:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = reactivate_tos_account(db, user)
    return _build_user_response(db, user)
