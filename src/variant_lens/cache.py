"""
SQLite-backed cache for API responses.

Key format: {source}:{identifier}:{version}
TTL per source, defined in config. Thread-safe via file locking.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import (
    CACHE_DIR,
    CACHE_TTL_CLINVAR,
    CACHE_TTL_GNOMAD,
    CACHE_TTL_PUBMED,
)


_DEFAULT_TTLS = {
    "gnomad": CACHE_TTL_GNOMAD,
    "clinvar": CACHE_TTL_CLINVAR,
    "pubmed": CACHE_TTL_PUBMED,
}


class Cache:
    """SQLite-backed cache for API responses."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (CACHE_DIR / "cache.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached value for a key, or None if missing or expired."""
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,),
            ).fetchone()

        if row is None:
            return None

        value_json, expires_at = row
        if expires_at < now:
            self.invalidate(key)
            return None

        return json.loads(value_json)

    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        """Store a value under a key with a time-to-live in seconds."""
        if ttl is None:
            ttl = self._ttl_for_key(key)

        expires_at = time.time() + ttl
        value_json = json.dumps(value)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cache (key, value, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at
                """,
                (key, value_json, expires_at),
            )

    def invalidate(self, key: str) -> None:
        """Remove a key from the cache."""
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))

    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._connect() as conn:
            conn.execute("DELETE FROM cache")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ttl_for_key(self, key: str) -> int:
        source = key.split(":", 1)[0]
        return _DEFAULT_TTLS.get(source, 24 * 3600)
