"""Settings endpoints: art-cache stats/clear and sign out."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import config, db

router = APIRouter(prefix="/api/settings", tags=["settings"])


class CacheStats(BaseModel):
    entries: int
    bytes: int
    cap_bytes: int


class Cleared(BaseModel):
    freed_bytes: int


class SignedOut(BaseModel):
    stage: str


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
