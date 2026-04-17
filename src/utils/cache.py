import pickle
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())


class _SQLiteCacheStore:
    """Small SQLite wrapper used as the primary cache persistence layer."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path.as_posix(), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                created_at_epoch REAL NOT NULL,
                expires_at_epoch REAL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cache_entries_expires
            ON cache_entries(expires_at_epoch)
            """
        )
        conn.commit()

    def get(self, key: str) -> Any | None:
        now_epoch = time.time()
        conn = self._connect()
        row = conn.execute(
            "SELECT value, expires_at_epoch FROM cache_entries WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        value_blob, expires_at_epoch = row
        if expires_at_epoch is not None and now_epoch >= float(expires_at_epoch):
            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
            conn.commit()
            return None
        return pickle.loads(value_blob)

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        created_at_epoch = time.time()
        expires_at_epoch = created_at_epoch + expire if expire is not None else None
        value_blob = pickle.dumps(value)
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO cache_entries(key, value, created_at_epoch, expires_at_epoch)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
                value = excluded.value,
                created_at_epoch = excluded.created_at_epoch,
                expires_at_epoch = excluded.expires_at_epoch
            """,
            (key, value_blob, created_at_epoch, expires_at_epoch),
        )
        conn.commit()

    def delete(self, key: str) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
        conn.commit()


class S3Cache:
    """Compatibility cache wrapper backed by local SQLite.

    ``s3_prefix`` is retained for API compatibility with older callers.
    """

    def __init__(self, directory: str, s3_prefix: str):
        self.sqlite_cache = _SQLiteCacheStore(Path(directory) / "cache.sqlite3")
        self.s3_prefix = s3_prefix.strip("/")

    def get(self, key: str, default: Any = None) -> Any:
        value = self.sqlite_cache.get(key)
        return value if value is not None else default

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        self.sqlite_cache.set(key, value, expire=expire)

    def delete(self, key: str) -> None:
        self.sqlite_cache.delete(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
