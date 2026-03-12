from app.schemas.base import ApiResponse


class HealthResponse(ApiResponse):
    data: dict[str, str]
    meta: dict[str, str]
