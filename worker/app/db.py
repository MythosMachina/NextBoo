from contextlib import contextmanager

from app.settings import get_settings
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


settings = get_settings()
pool = ConnectionPool(
    conninfo=(
        f"host={settings.postgres_host} port={settings.postgres_port} dbname={settings.postgres_db} "
        f"user={settings.postgres_user} password={settings.postgres_password}"
    ),
    kwargs={"row_factory": dict_row},
    min_size=1,
    max_size=max(4, settings.worker_concurrency),
)


@contextmanager
def get_connection() -> Connection:
    with pool.connection() as connection:
        yield connection
