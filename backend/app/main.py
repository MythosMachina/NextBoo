import threading

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine
from app.services.bootstrap import ensure_system_tags
from app.services.app_settings import ensure_sidebar_settings, ensure_tagger_settings
from app.api.v1.routes.tags import refresh_sidebar_cache_registry
from app.services.operations import sanitize_jobs_and_imports
from app.services.runtime_schema import (
    ensure_runtime_app_settings,
    ensure_runtime_auto_tagger_schema,
    ensure_runtime_invite_columns,
    ensure_runtime_rating_enums,
    ensure_runtime_user_columns,
)
from app.services.storage_sanitation import sanitize_gallery_storage
from fastapi import FastAPI
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
app.include_router(api_router, prefix="/api/v1")
app.mount("/media/content", StaticFiles(directory=settings.content_path), name="media-content")
app.mount("/media/content_thumbs", StaticFiles(directory=settings.thumb_path), name="media-thumbs")
sidebar_cache_stop_event = threading.Event()
sidebar_cache_thread: threading.Thread | None = None


@app.on_event("startup")
def on_startup() -> None:
    ensure_runtime_rating_enums(engine)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_user_columns(engine)
    ensure_runtime_invite_columns(engine)
    ensure_runtime_app_settings(engine)
    ensure_runtime_auto_tagger_schema(engine)
    with Session(engine) as session:
        ensure_system_tags(session)
        ensure_sidebar_settings(session)
        ensure_tagger_settings(session)
        sanitize_jobs_and_imports(session)
        sanitize_gallery_storage(session)
        session.commit()
    global sidebar_cache_thread
    if sidebar_cache_thread is None or not sidebar_cache_thread.is_alive():
        sidebar_cache_thread = threading.Thread(
            target=refresh_sidebar_cache_registry,
            args=(sidebar_cache_stop_event,),
            daemon=True,
            name="sidebar-cache-refresh",
        )
        sidebar_cache_thread.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    sidebar_cache_stop_event.set()
