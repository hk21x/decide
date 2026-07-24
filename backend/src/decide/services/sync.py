"""Library sync: full and incremental, with in-memory progress.

run_sync_blocking is the testable core (synchronous, runs in a worker
thread). SyncCoordinator is the async wrapper the routers and jobs use —
one sync at a time, progress readable at any point.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from .. import config, db
from ..sources.base import MediaSource, MovieRecord

log = logging.getLogger(__name__)

# Re-sync a small window before the last run so items updated while the
# previous sync was in flight are not missed.
INCREMENTAL_OVERLAP_S = 300

_UPSERT = """
INSERT INTO items (id, guid, imdb_id, tmdb_id, title, year, tagline, summary,
                   runtime_min, content_rating, audience_rating, genres_json,
                   directors_json, cast_json, collections_json, thumb, art,
                   view_count, last_viewed_at, added_at, updated_at, unusable,
                   synced_at)
VALUES (:id, :guid, :imdb_id, :tmdb_id, :title, :year, :tagline, :summary,
        :runtime_min, :content_rating, :audience_rating, :genres_json,
        :directors_json, :cast_json, :collections_json, :thumb, :art,
        :view_count, :last_viewed_at, :added_at, :updated_at, :unusable,
        :synced_at)
ON CONFLICT(id) DO UPDATE SET
    guid = excluded.guid, imdb_id = excluded.imdb_id, tmdb_id = excluded.tmdb_id,
    title = excluded.title, year = excluded.year, tagline = excluded.tagline,
    summary = excluded.summary, runtime_min = excluded.runtime_min,
    content_rating = excluded.content_rating,
    audience_rating = excluded.audience_rating, genres_json = excluded.genres_json,
    directors_json = excluded.directors_json, cast_json = excluded.cast_json,
    collections_json = excluded.collections_json,
    thumb = excluded.thumb, art = excluded.art, view_count = excluded.view_count,
    last_viewed_at = excluded.last_viewed_at, added_at = excluded.added_at,
    updated_at = excluded.updated_at, unusable = excluded.unusable,
    synced_at = excluded.synced_at
"""


def _row(rec: MovieRecord, synced_at: int) -> dict:
    return {
        "id": rec.id,
        "guid": rec.guid,
        "imdb_id": rec.imdb_id,
        "tmdb_id": rec.tmdb_id,
        "title": rec.title,
        "year": rec.year,
        "tagline": rec.tagline,
        "summary": rec.summary,
        "runtime_min": rec.runtime_min,
        "content_rating": rec.content_rating,
        "audience_rating": rec.audience_rating,
        "genres_json": json.dumps(rec.genres),
        "directors_json": json.dumps(rec.directors),
        "cast_json": json.dumps(rec.cast),
        "collections_json": json.dumps(rec.collections),
        "thumb": rec.thumb,
        "art": rec.art,
        "view_count": rec.view_count,
        "last_viewed_at": rec.last_viewed_at,
        "added_at": rec.added_at,
        "updated_at": rec.updated_at,
        # An unscraped file makes a terrible card (brief §4.2): no poster
        # AND no summary -> excluded from decks.
        "unusable": 0 if (rec.thumb or rec.summary) else 1,
        "synced_at": synced_at,
    }


@dataclass
class SyncOutcome:
    kind: str
    processed: int
    deleted: int
    started_at: int
    needs_full: bool = False


def run_sync_blocking(
    source: MediaSource,
    section_keys: list[str],
    full: bool,
    progress_cb: Callable[[int, int | None], None] | None = None,
) -> SyncOutcome:
    """Synchronous sync core. Call via db.run / asyncio.to_thread."""
    conn = db.connect()
    # Nanosecond watermark: two runs in the same second must still be
    # distinguishable, or the stale-row delete below misses everything.
    started_ns = time.time_ns()
    started = started_ns // 1_000_000_000

    updated_since: int | None = None
    if not full:
        last = config.get_value("last_sync_epoch")
        if last:
            updated_since = max(0, int(last) - INCREMENTAL_OVERLAP_S)
        else:
            full = True  # never synced -> full

    processed = 0
    for rec in source.fetch_movies(section_keys, updated_since, progress_cb):
        conn.execute(_UPSERT, _row(rec, started_ns))
        processed += 1
        if processed % 100 == 0:
            conn.commit()
    conn.commit()

    deleted = 0
    needs_full = False
    if full:
        cur = conn.execute(
            "DELETE FROM items WHERE synced_at < ? OR synced_at IS NULL", (started_ns,)
        )
        deleted = cur.rowcount
        conn.commit()

        # Collection tags are often missing from container listings, so on a
        # full sync we also walk the section's collections and merge their
        # memberships in (one request per collection — full sync only).
        try:
            memberships = source.collection_memberships(section_keys)
        except Exception:
            log.exception("collection sweep failed; per-item tags only")
            memberships = {}
        for item_id, names in memberships.items():
            row = conn.execute(
                "SELECT collections_json FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                continue
            merged = sorted(set(json.loads(row["collections_json"] or "[]")) | set(names))
            conn.execute(
                "UPDATE items SET collections_json = ? WHERE id = ?",
                (json.dumps(merged), item_id),
            )
        conn.commit()
    else:
        # Incremental filters cannot see removals: if the source total no
        # longer matches ours, flag that a full pass is needed.
        source_total = source.count_movies(section_keys)
        (our_total,) = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        if source_total != our_total:
            needs_full = True

    config.set_value("last_sync_epoch", str(started))
    return SyncOutcome(
        kind="full" if full else "incremental",
        processed=processed,
        deleted=deleted,
        started_at=started,
        needs_full=needs_full,
    )


@dataclass
class SyncProgress:
    state: str = "idle"  # idle | syncing
    kind: str | None = None
    processed: int = 0
    total: int | None = None
    error: str | None = None


class SyncCoordinator:
    def __init__(self, source_factory: Callable[[], MediaSource]):
        self.source_factory = source_factory
        self.progress = SyncProgress()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def run_now(self, full: bool) -> SyncOutcome | None:
        """Run a sync to completion. Returns None if one is already running."""
        if self._lock.locked():
            return None
        async with self._lock:
            self.progress = SyncProgress(
                state="syncing", kind="full" if full else "incremental"
            )

            def on_progress(processed: int, total: int | None) -> None:
                self.progress.processed = processed
                self.progress.total = total

            try:
                sections = await db.run(config.get_sections)
                if not sections:
                    raise RuntimeError("No library sections are configured yet.")
                source = await db.run(self.source_factory)
                outcome = await db.run(
                    run_sync_blocking, source, sections, full, on_progress
                )
                if outcome.needs_full:
                    log.info("incremental count mismatch; running full sync")
                    outcome = await db.run(
                        run_sync_blocking, source, sections, True, on_progress
                    )
                self.progress = SyncProgress(state="idle")
                return outcome
            except Exception as exc:
                log.exception("library sync failed")
                self.progress = SyncProgress(state="idle", error=str(exc))
                return None

    def trigger(self, full: bool) -> bool:
        """Fire-and-forget for the API. False if a sync is already running."""
        if self._lock.locked():
            return False
        self._task = asyncio.get_running_loop().create_task(self.run_now(full))
        return True
