"""Artwork disk cache with exact LRU via the art_cache table (constraint C2).

Files live under {data_dir}/art/. The SQLite index carries size, a strong
ETag (sha256, hashed once at write time) and last_used_at for eviction.
Per-key asyncio locks stop a deck load from stampeding the PMS.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .. import db

log = logging.getLogger(__name__)

TOUCH_THROTTLE_S = 3600
EVICT_TO_FRACTION = 0.9


class ArtCache:
    def __init__(self, root: Path, cap_bytes: int):
        self.root = root
        self.cap_bytes = cap_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.img"

    # ---- blocking helpers (call via db.run) ----

    def lookup_blocking(self, key: str) -> tuple[Path, str] | None:
        """Return (path, etag) on a hit, bumping last_used_at (throttled)."""
        conn = db.connect()
        row = conn.execute(
            "SELECT etag, last_used_at FROM art_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        path = self._path(key)
        if row is None or not path.exists():
            if row is not None:  # index row without a file — heal
                conn.execute("DELETE FROM art_cache WHERE cache_key = ?", (key,))
                conn.commit()
            return None
        now = int(time.time())
        if now - row["last_used_at"] > TOUCH_THROTTLE_S:
            conn.execute(
                "UPDATE art_cache SET last_used_at = ? WHERE cache_key = ?", (now, key)
            )
            conn.commit()
        return path, row["etag"]

    def store_blocking(self, key: str, data: bytes) -> tuple[Path, str]:
        etag = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)  # atomic
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        conn = db.connect()
        conn.execute(
            "INSERT INTO art_cache (cache_key, size_bytes, etag, last_used_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(cache_key) DO UPDATE SET size_bytes = excluded.size_bytes, "
            "etag = excluded.etag, last_used_at = excluded.last_used_at",
            (key, len(data), etag, int(time.time())),
        )
        conn.commit()
        self.evict_blocking()
        return path, etag

    def evict_blocking(self) -> int:
        """Delete oldest entries until under 90% of cap. Returns bytes freed."""
        conn = db.connect()
        (total,) = conn.execute("SELECT COALESCE(SUM(size_bytes), 0) FROM art_cache").fetchone()
        if total <= self.cap_bytes:
            return 0
        target = int(self.cap_bytes * EVICT_TO_FRACTION)
        freed = 0
        rows = conn.execute(
            "SELECT cache_key, size_bytes FROM art_cache ORDER BY last_used_at ASC"
        ).fetchall()
        for row in rows:
            if total - freed <= target:
                break
            self._path(row["cache_key"]).unlink(missing_ok=True)
            conn.execute(
                "DELETE FROM art_cache WHERE cache_key = ?", (row["cache_key"],)
            )
            freed += row["size_bytes"]
        conn.commit()
        if freed:
            log.info("art cache evicted %d bytes", freed)
        return freed

    def stats_blocking(self) -> tuple[int, int]:
        conn = db.connect()
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM art_cache"
        ).fetchone()
        return row[0], row[1]

    def clear_blocking(self) -> int:
        """Delete every cached file and index row. Returns bytes freed."""
        conn = db.connect()
        rows = conn.execute("SELECT cache_key, size_bytes FROM art_cache").fetchall()
        freed = 0
        for row in rows:
            self._path(row["cache_key"]).unlink(missing_ok=True)
            freed += row["size_bytes"]
        conn.execute("DELETE FROM art_cache")
        conn.commit()
        return freed

    # ---- async entry point ----

    async def get_or_fetch(
        self, key: str, fetch_blocking: Callable[[], bytes]
    ) -> tuple[Path, str]:
        """Return (path, etag), fetching and caching on miss.

        fetch_blocking runs in a worker thread and may raise — the caller
        turns that into a placeholder response.
        """
        hit = await db.run(self.lookup_blocking, key)
        if hit:
            return hit
        async with self._locks_guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = await db.run(self.lookup_blocking, key)  # lost the race?
            if hit:
                return hit
            data = await asyncio.to_thread(fetch_blocking)
            return await db.run(self.store_blocking, key, data)
