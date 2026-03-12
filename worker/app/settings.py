from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    project_name: str = Field(default="NextBoo", alias="PROJECT_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

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

    worker_concurrency: int = Field(default=2, alias="WORKER_CONCURRENCY")
    thumb_max_edge: int = Field(default=250, alias="THUMB_MAX_EDGE")
    tagger_provider: str = Field(default="camie", alias="TAGGER_PROVIDER")
    queue_name: str | None = Field(default=None, alias="QUEUE_NAME")
    stale_job_timeout_seconds: int = Field(default=300, alias="STALE_JOB_TIMEOUT_SECONDS")

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
    def ingest_queue_name(self) -> str:
        if self.queue_name:
            return self.queue_name
        provider = self.tagger_provider.strip().lower() if self.tagger_provider else "camie"
        return f"jobs:ingest:{provider}"

    @property
    def maintenance_queue_name(self) -> str:
        provider = self.tagger_provider.strip().lower() if self.tagger_provider else "camie"
        return f"jobs:maintenance:{provider}"

    @property
    def maintenance_running_key(self) -> str:
        provider = self.tagger_provider.strip().lower() if self.tagger_provider else "camie"
        return f"maintenance:{provider}:retag_all:running"

    @property
    def maintenance_pending_key(self) -> str:
        provider = self.tagger_provider.strip().lower() if self.tagger_provider else "camie"
        return f"maintenance:{provider}:retag_all:pending"


@lru_cache
def get_settings() -> Settings:
    return Settings()
