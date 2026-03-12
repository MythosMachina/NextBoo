from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    project_name: str = Field(default="NextBoo", alias="PROJECT_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    public_api_base_url: str = Field(default="http://localhost:18000", alias="PUBLIC_API_BASE_URL")

    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="nextboo", alias="POSTGRES_DB")
    postgres_user: str = Field(default="nextboo", alias="POSTGRES_USER")
    postgres_password: str = Field(default="nextboo", alias="POSTGRES_PASSWORD")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")

    queue_path: str = Field(default="/app/queue", alias="QUEUE_PATH")
    processing_path: str = Field(default="/app/processing", alias="PROCESSING_PATH")
    processing_failed_path: str = Field(default="/app/processing_failed", alias="PROCESSING_FAILED_PATH")
    content_path: str = Field(default="/app/content", alias="CONTENT_PATH")
    thumb_path: str = Field(default="/app/content_thumbs", alias="THUMB_PATH")
    import_path: str = Field(default="/app/imports", alias="IMPORT_PATH")
    model_path: str = Field(default="/models", alias="MODEL_PATH")

    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(default=43200, alias="REFRESH_TOKEN_EXPIRE_MINUTES")
    cors_origins: str = Field(default="http://localhost:13000", alias="CORS_ORIGINS")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_dsn(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def cors_origin_regex(self) -> str:
        return (
            r"^https?://("
            r"localhost|127\.0\.0\.1|"
            r"10(?:\.\d{1,3}){3}|"
            r"192\.168(?:\.\d{1,3}){2}|"
            r"172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}"
            r")(?::\d{1,5})?$"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
