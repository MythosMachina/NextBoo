from datetime import datetime, timezone
from typing import Annotated

from app.api.deps import DbSession, RedisClient, require_roles
from app.core.constants import UserRole
from app.models.board_import import BoardImportEvent, BoardImportRun
from app.models.user import User
from app.schemas.board_import import (
    BoardImportBoardItem,
    BoardImportBoardsResponse,
    BoardImportEventRead,
    BoardImportRunCreate,
    BoardImportRunDetailRead,
    BoardImportRunRead,
    BoardImportRunResponse,
    BoardImportRunsResponse,
)
from app.services.board_import.presets import get_preset
from app.services.board_import_runner import append_event, enqueue_board_import, supported_boards
from app.services.rate_limits import enforce_rate_limit
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, func


router = APIRouter(prefix="/admin/board-imports")


@router.get("/boards", response_model=BoardImportBoardsResponse)
def list_supported_boards(
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> BoardImportBoardsResponse:
    boards = [BoardImportBoardItem(**item) for item in supported_boards()]
    return BoardImportBoardsResponse(data=boards, meta={"count": len(boards)})


@router.get("/runs", response_model=BoardImportRunsResponse)
def list_board_import_runs(
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    page: int = 1,
    limit: int = 20,
) -> BoardImportRunsResponse:
    safe_page = max(page, 1)
    safe_limit = max(1, min(limit, 100))
    total_count = db.query(func.count(BoardImportRun.id)).scalar() or 0
    runs = (
        db.query(BoardImportRun)
        .order_by(desc(BoardImportRun.created_at))
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
        .all()
    )
    total_pages = max(1, (int(total_count) + safe_limit - 1) // safe_limit) if total_count else 1
    return BoardImportRunsResponse(
        data=[BoardImportRunRead.model_validate(item) for item in runs],
        meta={"count": len(runs), "page": safe_page, "limit": safe_limit, "total_count": int(total_count), "total_pages": total_pages},
    )


@router.get("/runs/{run_id}", response_model=BoardImportRunResponse)
def get_board_import_run(
    run_id: int,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> BoardImportRunResponse:
    run = db.get(BoardImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board import run not found")

    events = (
        db.query(BoardImportEvent)
        .filter(BoardImportEvent.run_id == run_id)
        .order_by(desc(BoardImportEvent.id))
        .limit(200)
        .all()
    )
    payload = BoardImportRunDetailRead.model_validate(run)
    payload.events = [BoardImportEventRead.model_validate(event) for event in reversed(events)]
    return BoardImportRunResponse(data=payload, meta={"event_count": len(events)})


@router.post("/runs", response_model=BoardImportRunResponse)
def create_board_import_run(
    payload: BoardImportRunCreate,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> BoardImportRunResponse:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    if payload.all_boards:
        presets = [get_preset(item["name"]) for item in supported_boards()]
    else:
        try:
            presets = [get_preset(payload.board_name.strip())]
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    created_runs: list[BoardImportRun] = []
    for preset in presets:
        run = BoardImportRun(
            board_name=preset.name,
            tag_query=payload.tags.strip(),
            requested_limit=max(payload.requested_limit, 1),
            hourly_limit=1000,
            status="pending",
            submitted_by_user_id=current_user.id,
            current_message="Queued for board import.",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        enqueue_board_import(run.id)
        created_runs.append(run)

    run = created_runs[0]
    return BoardImportRunResponse(
        data=BoardImportRunDetailRead.model_validate(run),
        meta={"status": "queued", "queued_count": len(created_runs), "all_boards": int(payload.all_boards)},
    )


@router.post("/runs/{run_id}/stop", response_model=BoardImportRunResponse)
def stop_board_import_run(
    run_id: int,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> BoardImportRunResponse:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    run = db.get(BoardImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board import run not found")
    if run.status not in {"pending", "running", "retrying"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active runs can be stopped")

    run.status = "cancelled"
    run.finished_at = datetime.now(timezone.utc)
    run.current_message = "Board import was cancelled."
    db.add(run)
    db.commit()
    db.refresh(run)
    append_event(db, run, level="warning", event_type="cancelled", message=run.current_message)
    payload = BoardImportRunDetailRead.model_validate(run)
    payload.events = []
    return BoardImportRunResponse(data=payload, meta={"status": "cancelled"})


@router.post("/runs/{run_id}/retry", response_model=BoardImportRunResponse)
def retry_board_import_run(
    run_id: int,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> BoardImportRunResponse:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    run = db.get(BoardImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board import run not found")
    if run.status in {"pending", "running", "retrying"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stop or finish the active run before retrying it")

    retry_run = BoardImportRun(
        board_name=run.board_name,
        tag_query=run.tag_query,
        requested_limit=run.requested_limit,
        hourly_limit=run.hourly_limit,
        status="pending",
        submitted_by_user_id=current_user.id,
        current_message=f"Retry queued from run #{run.id}.",
    )
    db.add(retry_run)
    db.commit()
    db.refresh(retry_run)
    enqueue_board_import(retry_run.id)
    payload = BoardImportRunDetailRead.model_validate(retry_run)
    payload.events = []
    return BoardImportRunResponse(data=payload, meta={"status": "queued", "retry_of": run.id})


@router.delete("/runs/{run_id}")
def delete_board_import_run(
    run_id: int,
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
) -> dict[str, int | str]:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)
    run = db.get(BoardImportRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board import run not found")
    if run.status in {"pending", "running", "retrying"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active runs must be stopped before removal")

    db.delete(run)
    db.commit()
    return {"status": "deleted", "run_id": run_id}


@router.delete("/runs")
def bulk_delete_board_import_runs(
    db: DbSession,
    redis_client: RedisClient,
    request: Request,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MODERATOR))],
    status_filter: str,
) -> dict[str, int | str]:
    enforce_rate_limit(db, redis_client, request, "admin_write", current_user=current_user)

    if status_filter == "done":
        query = db.query(BoardImportRun).filter(BoardImportRun.status == "done")
    elif status_filter == "failed":
        query = db.query(BoardImportRun).filter(BoardImportRun.status.in_(["failed", "cancelled"]))
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported status filter")

    runs = query.all()
    deleted_count = 0
    for run in runs:
        db.delete(run)
        deleted_count += 1
    db.commit()
    return {"status": "deleted", "deleted_count": deleted_count, "status_filter": status_filter}
