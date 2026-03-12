from collections.abc import Generator

from app.core.config import get_settings
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


settings = get_settings()

engine = create_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_redis_client() -> Redis:
    return Redis.from_url(settings.redis_dsn, decode_responses=True)
