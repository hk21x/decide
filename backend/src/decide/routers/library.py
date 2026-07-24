from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import config, db
from ..models import (
    DeckFilters,
    LibraryFilters,
    LibraryStatus,
    PreviewCount,
    SyncRequest,
    SyncStarted,
)
from ..services import deck as deck_service

router = APIRouter(prefix="/api/library", tags=["library"])
filters_router = APIRouter(prefix="/api/filters", tags=["library"])


def filters_from_query(
    unwatched_only: bool = True,
    genres: str = Query(default="", description="Comma-separated genre list"),
    year_min: int | None = Query(default=None, ge=1880, le=2100),
    year_max: int | None = Query(default=None, ge=1880, le=2100),
    max_runtime: int | None = Query(default=None, ge=30, le=600),
    min_rating: float | None = Query(default=None, ge=0, le=10),
    certificate: str | None = Query(default=None),
    collection: str | None = Query(default=None, max_length=200),
) -> DeckFilters:
    return DeckFilters(
        unwatched_only=unwatched_only,
        genres=[g.strip() for g in genres.split(",") if g.strip()],
        year_min=year_min,
        year_max=year_max,
        max_runtime=max_runtime,
        min_rating=min_rating,
        certificate=certificate,  # validated by the model
        collection=collection or None,
    )


@router.post("/sync", response_model=SyncStarted, status_code=202)
async def trigger_sync(body: SyncRequest, request: Request) -> SyncStarted:
    stage = await db.run(config.setup_stage)
    if stage != "ready":
        raise HTTPException(
            status_code=409, detail="Set up the Plex connection before syncing."
        )
    if not request.app.state.sync.trigger(body.full):
        raise HTTPException(status_code=409, detail="A sync is already running.")
    return SyncStarted(started=True)


@router.get("/filters", response_model=LibraryFilters)
async def library_filters() -> LibraryFilters:
    def _read() -> LibraryFilters:
        conn = db.connect()
        genres = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT value FROM items, json_each(items.genres_json) "
                "WHERE items.unusable = 0 ORDER BY value"
            )
        ]
        decades = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT (year / 10) * 10 FROM items "
                "WHERE year IS NOT NULL AND unusable = 0 ORDER BY 1"
            )
        ]
        # Collections with at least 2 usable films — a 1-film deck is no deck.
        collections = [
            r[0]
            for r in conn.execute(
                "SELECT value, COUNT(*) AS n FROM items, "
                "json_each(items.collections_json) WHERE items.unusable = 0 "
                "GROUP BY value HAVING n >= 2 ORDER BY value"
            )
        ]
        return LibraryFilters(
            genres=genres,
            decades=decades,
            certificates=deck_service.CEILING_OPTIONS,
            collections=collections,
        )

    return await db.run(_read)


@filters_router.get("/preview", response_model=PreviewCount)
async def preview(filters: DeckFilters = Depends(filters_from_query)) -> PreviewCount:
    return PreviewCount(count=await db.run(deck_service.preview_count, filters))


@router.get("/status", response_model=LibraryStatus)
async def library_status(request: Request) -> LibraryStatus:
    def _read():
        conn = db.connect()
        (count,) = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        (unusable,) = conn.execute(
            "SELECT COUNT(*) FROM items WHERE unusable = 1"
        ).fetchone()
        last = config.get_value("last_sync_epoch")
        return (
            count,
            unusable,
            int(last) if last else None,
            config.setup_stage(),
            config.get_sections(),
        )

    count, unusable, last, stage, sections = await db.run(_read)
    progress = request.app.state.sync.progress
    return LibraryStatus(
        stage=stage,
        state=progress.state,
        kind=progress.kind,
        processed=progress.processed,
        total=progress.total,
        error=progress.error,
        item_count=count,
        unusable_count=unusable,
        last_synced_at=last,
        sections=sections,
    )
