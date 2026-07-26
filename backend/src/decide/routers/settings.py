"""Settings endpoints: art-cache stats/clear and sign out."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import config, db
from ..models import AccessConfig, AccessUpdate
from ..services import access as access_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


class CacheStats(BaseModel):
    entries: int
    bytes: int
    cap_bytes: int


class Cleared(BaseModel):
    freed_bytes: int


class SignedOut(BaseModel):
    stage: str


@router.get("/access", response_model=AccessConfig)
async def get_access() -> AccessConfig:
    port = config._settings().port

    def _stored() -> tuple[str | None, str | None]:
        settings = config._settings()
        return (
            settings.env_local_url or config.get_value("access_local_url"),
            settings.env_remote_url or config.get_value("access_remote_url"),
        )

    local, remote = await db.run(_stored)
    detected_local = await asyncio.to_thread(access_service.detect_local_url, port)
    detected_remote = await asyncio.to_thread(access_service.detect_tailscale_url, port)
    return AccessConfig(
        local_url=local,
        remote_url=remote,
        detected_local=detected_local,
        detected_remote=detected_remote,
    )


@router.put("/access", response_model=AccessConfig)
async def set_access(body: AccessUpdate) -> AccessConfig:
    def _store() -> None:
        for key, value in (
            ("access_local_url", body.local_url.strip().rstrip("/")),
            ("access_remote_url", body.remote_url.strip().rstrip("/")),
        ):
            if value:
                config.set_value(key, value)
            else:
                config.delete_value(key)

    await db.run(_store)
    return await get_access()


@router.get("/cache", response_model=CacheStats)
async def cache_stats(request: Request) -> CacheStats:
    entries, size = await db.run(request.app.state.artcache.stats_blocking)
    return CacheStats(
        entries=entries, bytes=size, cap_bytes=request.app.state.artcache.cap_bytes
    )


@router.post("/cache/clear", response_model=Cleared)
async def clear_cache(request: Request) -> Cleared:
    freed = await db.run(request.app.state.artcache.clear_blocking)
    return Cleared(freed_bytes=freed)


@router.post("/signout", response_model=SignedOut)
async def sign_out() -> SignedOut:
    """Forget the Plex connection. Library items stay (harmless without a
    token) so re-connecting to the same server is instant."""

    def _forget() -> None:
        for key in (
            "plex_token",
            "plex_access_token",
            "plex_url",
            "plex_sections",
            "server_machine_id",
            "server_name",
        ):
            config.delete_value(key)

    await db.run(_forget)
    return SignedOut(stage=await db.run(config.setup_stage))
