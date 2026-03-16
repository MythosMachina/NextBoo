from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_STATE_PATH = Path.home() / ".local" / "share" / "borooimport" / "state.sqlite3"
WINDOW_SECONDS = 3600
DEFAULT_HOURLY_LIMIT = 1000


@dataclass(slots=True)
class HourlyBudget:
    state_path: Path = DEFAULT_STATE_PATH
    hourly_limit: int = DEFAULT_HOURLY_LIMIT

    def __post_init__(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.state_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists imported_posts (
                    board text not null,
                    remote_post_id text not null,
                    imported_at real not null,
                    nextboo_image_id text,
                    primary key (board, remote_post_id)
                )
                """
            )
            conn.commit()

    def _prune(self, conn: sqlite3.Connection, now: float) -> None:
        conn.execute(
            "delete from imported_posts where imported_at < ?",
            (now - WINDOW_SECONDS,),
        )

    def remaining(self) -> int:
        now = time.time()
        with self._connect() as conn:
            self._prune(conn, now)
            (count,) = conn.execute(
                "select count(*) from imported_posts where imported_at >= ?",
                (now - WINDOW_SECONDS,),
            ).fetchone()
            return max(self.hourly_limit - int(count), 0)

    def seen(self, board: str, remote_post_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "select 1 from imported_posts where board = ? and remote_post_id = ?",
                (board, remote_post_id),
            ).fetchone()
            return row is not None

    def record(self, board: str, remote_post_id: str, nextboo_image_id: str | None = None) -> None:
        now = time.time()
        with self._connect() as conn:
            self._prune(conn, now)
            conn.execute(
                """
                insert into imported_posts (board, remote_post_id, imported_at, nextboo_image_id)
                values (?, ?, ?, ?)
                on conflict(board, remote_post_id) do update set
                    imported_at = excluded.imported_at,
                    nextboo_image_id = excluded.nextboo_image_id
                """,
                (board, remote_post_id, now, nextboo_image_id),
            )
            conn.commit()
