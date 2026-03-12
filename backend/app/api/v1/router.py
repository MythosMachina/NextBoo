from app.api.v1.routes import app_settings, auth, health, images, invites, jobs, moderation, search, strikes, tags, upload_requests, uploads, users
from fastapi import APIRouter


api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(app_settings.router, tags=["app-settings"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(invites.router, tags=["invites"])
api_router.include_router(images.router, tags=["images"])
api_router.include_router(moderation.router, tags=["moderation"])
api_router.include_router(strikes.router, tags=["strikes"])
api_router.include_router(tags.router, tags=["tags"])
api_router.include_router(search.router, tags=["search"])
api_router.include_router(jobs.router, tags=["jobs"])
api_router.include_router(upload_requests.router, tags=["upload-requests"])
api_router.include_router(uploads.router, tags=["uploads"])
