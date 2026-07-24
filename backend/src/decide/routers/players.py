"""Play on the TV: list controllable Plex clients, send a film to one."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from ..models import PlayerEntry, PlayersResponse, PlayRequest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/players", tags=["players"])


@router.get("", response_model=PlayersResponse)
async def list_players(request: Request) -> PlayersResponse:
    try:
        source = await asyncio.to_thread(request.app.state.source_factory)
        players = await asyncio.to_thread(source.list_players)
    except Exception as exc:
        log.info("player discovery failed: %s", type(exc).__name__)
        players = []
    return PlayersResponse(
        players=[
            PlayerEntry(id=p.id, name=p.name, product=p.product) for p in players
        ]
    )


@router.post("/play")
async def play(body: PlayRequest, request: Request) -> dict:
    try:
        source = await asyncio.to_thread(request.app.state.source_factory)
        await asyncio.to_thread(source.play_on, body.item_id, body.player_id)
    except Exception as exc:
        log.info("play_on failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Couldn't reach that player. Check Plex is open on it, then try again.",
        ) from None
    return {"sent": True}
