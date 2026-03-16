import threading
import warnings

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine
from app.services.bootstrap import ensure_system_tags
from app.services.backup_exports import backup_export_worker_loop, ensure_backup_export_directory
from app.services.board_import_runner import board_import_worker_loop, ensure_boroo_uploader_user
from app.services.app_settings import (
    ensure_autoscaler_settings,
    ensure_near_duplicate_settings,
    ensure_rate_limit_settings,
    ensure_sidebar_settings,
    ensure_tagger_settings,
)
from app.api.v1.routes.tags import refresh_sidebar_cache_registry
from app.services.operations import sanitize_jobs_and_imports
from app.services.runtime_schema import (
    ensure_runtime_app_settings,
    ensure_runtime_auto_tagger_schema,
    ensure_runtime_backup_export_schema,
    ensure_runtime_board_import_schema,
    ensure_runtime_comment_schema,
    ensure_runtime_danger_tag_schema,
    ensure_runtime_near_duplicate_schema,
    ensure_runtime_invite_columns,
    ensure_runtime_rating_enums,
    ensure_runtime_user_columns,
    ensure_runtime_vote_schema,
)
from app.services.storage_sanitation import sanitize_gallery_storage
from app.services.tos import purge_expired_tos_deactivated_users
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session


settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
app.include_router(api_router, prefix="/api/v1")
app.mount("/media/content", StaticFiles(directory=settings.content_path), name="media-content")
app.mount("/media/content_thumbs", StaticFiles(directory=settings.thumb_path), name="media-thumbs")
sidebar_cache_stop_event = threading.Event()
sidebar_cache_thread: threading.Thread | None = None
board_import_stop_event = threading.Event()
board_import_thread: threading.Thread | None = None
backup_export_stop_event = threading.Event()
backup_export_thread: threading.Thread | None = None


@app.on_event("startup")
def on_startup() -> None:
    if settings.jwt_secret == "change-me":
        warnings.warn("JWT_SECRET is using the insecure default. Set a strong secret before public deployment.")
    ensure_runtime_rating_enums(engine)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_user_columns(engine)
    ensure_runtime_invite_columns(engine)
    ensure_runtime_app_settings(engine)
    ensure_runtime_auto_tagger_schema(engine)
    ensure_runtime_comment_schema(engine)
    ensure_runtime_board_import_schema(engine)
    ensure_runtime_backup_export_schema(engine)
    ensure_runtime_danger_tag_schema(engine)
    ensure_runtime_near_duplicate_schema(engine)
    ensure_runtime_vote_schema(engine)
    with Session(engine) as session:
        ensure_system_tags(session)
        ensure_boroo_uploader_user(session)
        ensure_sidebar_settings(session)
        ensure_rate_limit_settings(session)
        ensure_autoscaler_settings(session)
        ensure_tagger_settings(session)
        ensure_near_duplicate_settings(session)
        purge_expired_tos_deactivated_users(session)
        sanitize_jobs_and_imports(session)
        sanitize_gallery_storage(session)
        session.commit()
    ensure_backup_export_directory()
    global sidebar_cache_thread
    if sidebar_cache_thread is None or not sidebar_cache_thread.is_alive():
        sidebar_cache_thread = threading.Thread(
            target=refresh_sidebar_cache_registry,
            args=(sidebar_cache_stop_event,),
            daemon=True,
            name="sidebar-cache-refresh",
        )
        sidebar_cache_thread.start()
    global board_import_thread
    if board_import_thread is None or not board_import_thread.is_alive():
        board_import_thread = threading.Thread(
            target=board_import_worker_loop,
            args=(board_import_stop_event,),
            daemon=True,
            name="board-import-runner",
        )
        board_import_thread.start()
    global backup_export_thread
    if backup_export_thread is None or not backup_export_thread.is_alive():
        backup_export_thread = threading.Thread(
            target=backup_export_worker_loop,
            args=(backup_export_stop_event,),
            daemon=True,
            name="backup-export-runner",
        )
        backup_export_thread.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    sidebar_cache_stop_event.set()
    board_import_stop_event.set()
    backup_export_stop_event.set()
