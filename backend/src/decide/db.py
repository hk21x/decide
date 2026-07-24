"""SQLite access layer.

Stdlib sqlite3 with one connection per (worker thread, db path). All route
handlers are async; blocking DB work goes through ``await db.run(fn, ...)``
which executes in a thread so the event loop never blocks.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

_local = threading.local()
_db_path: Path | None = None


def configure(path: Path) -> None:
    global _db_path
    _db_path = path
    path.parent.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    """Return this thread's connection to the configured database."""
    if _db_path is None:
        raise RuntimeError("db.configure() has not been called")
    conns: dict[str, sqlite3.Connection] = getattr(_local, "conns", None) or {}
    _local.conns = conns
    key = str(_db_path)
    conn = conns.get(key)
    if conn is None:
        conn = sqlite3.connect(key, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conns[key] = conn
    return conn


async def run(fn: Callable, *args, **kwargs):
    """Run a blocking function (typically using db.connect()) off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)
