"""Setup wizard endpoints.

PIN login state is in-process: POST /pin creates a plex.tv PIN and parks the
MyPlexPinLogin object in app.state.pins under an opaque id; GET /pin/{id}
polls it. Tokens go straight into the config table and are never returned.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request

from .. import config, db, security
from ..models import (
    PinPoll,
    PinStart,
    SectionEntry,
    ServerEntry,
    SetupServerRequest,
    SetupServerResponse,
    SetupStatus,
)
from ..sources import plex

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])

PIN_MAX_AGE_S = 30 * 60


@dataclass
class PinEntry:
    login: object
    created: float = field(default_factory=time.time)


def _gc_pins(pins: dict[str, PinEntry]) -> None:
    cutoff = time.time() - PIN_MAX_AGE_S
    for pin_id in [k for k, v in pins.items() if v.created < cutoff]:
        del pins[pin_id]


@router.get("/status", response_model=SetupStatus)
async def setup_status() -> SetupStatus:
    def _read() -> SetupStatus:
        machine_id, name = config.get_server_identity()
        return SetupStatus(
            stage=config.setup_stage(),
            server_name=name,
            machine_id=machine_id,
            sections=config.get_sections(),
        )

    return await db.run(_read)


@router.post("/pin", response_model=PinStart)
async def start_pin(request: Request) -> PinStart:
    import uuid

    _gc_pins(request.app.state.pins)
    login = await asyncio.to_thread(plex.start_pin_login, request.app.state.client_id)
    pin_id = uuid.uuid4().hex
    request.app.state.pins[pin_id] = PinEntry(login)
    return PinStart(id=pin_id, code=login.pin)


@router.get("/pin/{pin_id}", response_model=PinPoll)
async def poll_pin(pin_id: str, request: Request) -> PinPoll:
    entry: PinEntry | None = request.app.state.pins.get(pin_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown or expired sign-in attempt. Start the sign-in again.",
        )
    token = await asyncio.to_thread(plex.check_pin_login, entry.login)
    if token:
        security.add_secret(token)
        await db.run(config.set_value, "plex_token", token)
        servers = await asyncio.to_thread(plex.discover_servers, token)
        request.app.state.discovered = {s.machine_id: s for s in servers}
        for s in servers:
            security.add_secret(s.access_token)
        del request.app.state.pins[pin_id]
        return PinPoll(
            authenticated=True,
            servers=[
                ServerEntry(name=s.name, machine_id=s.machine_id, owned=s.owned)
                for s in servers
            ],
        )
    expired = bool(getattr(entry.login, "expired", False))
    if expired:
        request.app.state.pins.pop(pin_id, None)
    return PinPoll(authenticated=False, expired=expired)


@router.post("/server", response_model=SetupServerResponse)
async def choose_server(body: SetupServerRequest, request: Request) -> SetupServerResponse:
    if body.token:
        security.add_secret(body.token)
        await db.run(config.set_value, "plex_token", body.token)

    token = await db.run(config.get_plex_token)
    if not token:
        raise HTTPException(
            status_code=400, detail="Sign in with Plex first, or paste a token."
        )

    access_token = token
    server_name: str | None = None

    if body.url:
        candidates = [body.url]
    elif body.machine_id:
        discovered = request.app.state.discovered.get(body.machine_id)
        if discovered is None:
            servers = await asyncio.to_thread(plex.discover_servers, token)
            request.app.state.discovered = {s.machine_id: s for s in servers}
            discovered = request.app.state.discovered.get(body.machine_id)
        if discovered is None:
            raise HTTPException(
                status_code=404, detail="That server isn't on your Plex account."
            )
        candidates = plex.candidate_urls(discovered)
        server_name = discovered.name
        if discovered.access_token:
            access_token = discovered.access_token
            security.add_secret(access_token)
    else:
        stored = await db.run(config.get_plex_url)
        if not stored:
            raise HTTPException(
                status_code=400,
                detail="Provide a server URL, or pick a server discovered from your account.",
            )
        candidates = [stored]
        access_token = (await db.run(config.get_value, "plex_access_token")) or token

    source = None
    info = None
    for candidate in candidates:
        try:
            attempt = plex.PlexSource(candidate, access_token)
            info = await asyncio.to_thread(attempt.test_connection)
            source = attempt
            chosen_url = candidate
            break
        except Exception as exc:  # try the next connection candidate
            log.info("connection attempt failed for %s: %s", candidate, type(exc).__name__)
    if source is None or info is None:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Can't reach Plex at {candidates[0]}. "
                "Check the server is running and reachable, then try again."
            ),
        )

    def _store() -> None:
        config.set_value("plex_url", chosen_url)
        config.set_value("plex_access_token", access_token)
        config.set_value("server_machine_id", info.machine_identifier)
        config.set_value("server_name", server_name or info.friendly_name)

    await db.run(_store)

    available = await asyncio.to_thread(source.list_movie_sections)
    entries = [
        SectionEntry(key=s.key, title=s.title, movie_count=s.movie_count)
        for s in available
    ]

    if body.sections:
        valid = {s.key for s in available}
        unknown = [k for k in body.sections if k not in valid]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown library sections: {', '.join(unknown)}. Pick from the offered list.",
            )
        await db.run(config.set_value, "plex_sections", json.dumps(body.sections))
        request.app.state.sync.trigger(full=True)
        return SetupServerResponse(
            stage="ready",
            server_name=server_name or info.friendly_name,
            machine_id=info.machine_identifier,
            available_sections=entries,
        )

    return SetupServerResponse(
        stage="needs_sections",
        server_name=server_name or info.friendly_name,
        machine_id=info.machine_identifier,
        available_sections=entries,
    )
