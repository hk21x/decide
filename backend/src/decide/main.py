from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, jobs, migrations, security
from .events import ConnectionManager
from .routers import (
    album,
    art,
    health,
    library,
    live,
    players,
    sessions,
    settings as settings_router,
    setup,
)
from .services.artcache import ArtCache
from .services.sync import SyncCoordinator
from .sources import plex
from .sources.plex import PlexSource

log = logging.getLogger("decide")


def _make_source() -> PlexSource:
    """Default MediaSource factory: PlexSource from stored config.
    Runs inside a worker thread (config getters touch SQLite)."""
    url = config.get_plex_url()
    token = config.get_server_token()
    if not url or not token:
        raise RuntimeError("Plex connection is not configured.")
    return PlexSource(url, token)


def _ensure_client_id() -> str:
    client_id = config.get_value("client_identifier")
    if not client_id:
        client_id = str(uuid.uuid4())
        config.set_value("client_identifier", client_id)
    return client_id


def _item_count() -> int:
    (count,) = db.connect().execute("SELECT COUNT(*) FROM items").fetchone()
    return count


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    config.init(settings)
    db.configure(settings.data_dir / "decide.db")
    await db.run(migrations.apply)
    await db.run(security.bootstrap)
    security.install_redaction()

    # Register every stored secret with the log redaction filter (C1).
    security.add_secret(settings.env_plex_token)
    for key in ("plex_token", "plex_access_token"):
        security.add_secret(await db.run(config.get_value, key))

    app.state.client_id = await db.run(_ensure_client_id)
    await asyncio.to_thread(plex.apply_client_identity, app.state.client_id)

    app.state.pins = {}
    app.state.discovered = {}
    app.state.events = ConnectionManager()
    app.state.source_factory = _make_source
    app.state.sync = SyncCoordinator(lambda: app.state.source_factory())
    app.state.artcache = ArtCache(
        root=settings.data_dir / "art",
        cap_bytes=settings.art_cache_mb * 1024 * 1024,
    )

    tasks = jobs.start_jobs(app) if settings.enable_jobs else []

    # Declarative env config: if we boot fully configured with an empty
    # library, run the first sync without waiting to be asked.
    if await db.run(config.setup_stage) == "ready" and await db.run(_item_count) == 0:
        app.state.sync.trigger(full=True)

    log.info("Decide started (data dir %s)", settings.data_dir)
    yield

    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load_settings()
    app = FastAPI(title="Decide", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    app.include_router(setup.router)
    app.include_router(library.router)
    app.include_router(library.filters_router)
    app.include_router(sessions.router)
    app.include_router(art.router)
    app.include_router(live.router)
    app.include_router(settings_router.router)
    app.include_router(album.router)
    app.include_router(players.router)

    if settings.static_dir and settings.static_dir.exists():
        static_dir = settings.static_dir
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        # SPA catch-all: real files served as-is, every other path gets
        # index.html so client-side routes survive a refresh. Registered
        # after the API routers, so /api always wins.
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            candidate = (static_dir / full_path).resolve()
            if (
                full_path
                and candidate.is_relative_to(static_dir.resolve())
                and candidate.is_file()
            ):
                return FileResponse(candidate)
            return FileResponse(
                static_dir / "index.html",
                headers={"Cache-Control": "no-cache, must-revalidate"},
            )

    return app


app = create_app()
