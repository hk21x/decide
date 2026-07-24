"""Background jobs: incremental sync (6 h) and purge (15 min).

Plain asyncio tasks started from lifespan. Each job's last run is persisted
in the config table so a container restart does not reset the clock.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from . import config, db

log = logging.getLogger(__name__)

SESSION_HARD_DELETE_S = 7 * 86400


async def periodic(name: str, interval_s: int, fn: Callable[[], Awaitable[None]]) -> None:
    while True:
        raw = await db.run(config.get_value, f"job:{name}:last_run")
        last = int(raw) if raw else 0
        delay = max(0.0, last + interval_s - time.time())
        await asyncio.sleep(delay)
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("job %s failed; will retry next interval", name)
        await db.run(config.set_value, f"job:{name}:last_run", str(int(time.time())))


def start_jobs(app) -> list[asyncio.Task]:
    settings = app.state.settings

    async def incremental() -> None:
        if await db.run(config.setup_stage) == "ready":
            await app.state.sync.run_now(full=False)

    async def purge() -> None:
        await db.run(purge_blocking)
        await db.run(app.state.artcache.evict_blocking)

    return [
        asyncio.create_task(
            periodic("incremental_sync", settings.incremental_interval_s, incremental),
            name="job-incremental-sync",
        ),
        asyncio.create_task(
            periodic("purge", settings.purge_interval_s, purge), name="job-purge"
        ),
    ]


def purge_blocking() -> None:
    """Expire sessions past expires_at; hard-delete after 7 days."""
    now = int(time.time())
    conn = db.connect()
    conn.execute(
        "UPDATE sessions SET state = 'expired' WHERE expires_at < ? AND state != 'expired'",
        (now,),
    )
    cutoff = now - SESSION_HARD_DELETE_S
    stale = [
        r[0] for r in conn.execute("SELECT id FROM sessions WHERE created_at < ?", (cutoff,))
    ]
    for session_id in stale:
        conn.execute("DELETE FROM swipes WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM matches WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM participants WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
