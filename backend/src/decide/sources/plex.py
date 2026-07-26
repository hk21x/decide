"""PlexSource — the only module that imports plexapi.

plexapi is synchronous; every call into this module must be wrapped in
asyncio.to_thread by the caller. See docs/plex-notes.md for the verified
endpoint and object shapes (dated 22 July 2026).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import requests

from .base import (
    DeepLink,
    MovieRecord,
    PlayerInfo,
    ProgressCallback,
    Section,
    ServerInfo,
)

log = logging.getLogger(__name__)

PAGE_SIZE = 200
PRODUCT = "Decide"  # renamed from "Matinee" 23 Jul 2026; the plex.tv devices
# entry created under the old name persists until re-auth — cosmetic only.


def apply_client_identity(client_id: str, version: str = "0.1.0") -> None:
    """Pin a stable X-Plex-Client-Identifier / product name process-wide.

    Belt and braces: set the module constants AND mutate BASE_HEADERS in
    place, since other plexapi modules may hold a reference to the dict.
    (plex-notes.md §1 — flagged verify-at-M1.)
    """
    import plexapi

    plexapi.X_PLEX_IDENTIFIER = client_id
    plexapi.X_PLEX_PRODUCT = PRODUCT
    plexapi.X_PLEX_VERSION = version
    plexapi.BASE_HEADERS.update(
        {
            "X-Plex-Client-Identifier": client_id,
            "X-Plex-Product": PRODUCT,
            "X-Plex-Version": version,
            "X-Plex-Device-Name": PRODUCT,
        }
    )


def identity_headers(client_id: str) -> dict[str, str]:
    return {
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Product": PRODUCT,
        "X-Plex-Device-Name": PRODUCT,
    }


# ---------------------------------------------------------------- PIN login

def start_pin_login(client_id: str):
    """Create a plex.tv PIN (4-char link code). Returns the MyPlexPinLogin
    object — hold it in memory and poll check_pin_login() with it."""
    from plexapi.myplex import MyPlexPinLogin

    return MyPlexPinLogin(headers=identity_headers(client_id), oauth=False)


def check_pin_login(pin_login) -> str | None:
    """One poll. Returns the account token once the user has linked, else None."""
    if pin_login.checkLogin():
        return pin_login.token
    return None


# ------------------------------------------------------------- discovery

@dataclass
class ConnectionCandidate:
    uri: str
    local: bool
    relay: bool


@dataclass
class DiscoveredServer:
    name: str
    machine_id: str
    owned: bool
    access_token: str | None
    connections: list[ConnectionCandidate]


def discover_servers(token: str) -> list[DiscoveredServer]:
    from plexapi.myplex import MyPlexAccount

    account = MyPlexAccount(token=token)
    servers: list[DiscoveredServer] = []
    for res in account.resources():
        if "server" not in (res.provides or ""):
            continue
        conns: list[ConnectionCandidate] = []
        for c in res.connections or []:
            # Direct http to the LAN address first (works with no internet,
            # C6); the plex.direct https uri as fallback.
            if getattr(c, "local", False) and getattr(c, "address", None):
                conns.append(
                    ConnectionCandidate(
                        uri=f"http://{c.address}:{c.port}", local=True, relay=False
                    )
                )
            conns.append(
                ConnectionCandidate(
                    uri=c.uri,
                    local=bool(getattr(c, "local", False)),
                    relay=bool(getattr(c, "relay", False)),
                )
            )
        servers.append(
            DiscoveredServer(
                name=res.name,
                machine_id=res.clientIdentifier,
                owned=bool(getattr(res, "owned", True)),
                access_token=getattr(res, "accessToken", None),
                connections=conns,
            )
        )
    return servers


def candidate_urls(server: DiscoveredServer) -> list[str]:
    """Connection attempts in preference order: local non-relay, then remote
    non-relay, then relay (last resort — routes through Plex infra)."""
    ordered = sorted(server.connections, key=lambda c: (not c.local, c.relay))
    seen: set[str] = set()
    urls = []
    for c in ordered:
        if c.uri not in seen:
            urls.append(c.uri)
            seen.add(c.uri)
    return urls


# ------------------------------------------------------------- the source

class PlexSource:
    """MediaSource implementation for Plex Media Server."""

    def __init__(self, base_url: str, token: str, timeout: int = 15):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._server_obj = None
        self._http = requests.Session()
        self._http.headers.update({"X-Plex-Token": token, "Accept": "image/*"})

    def _server(self):
        if self._server_obj is None:
            from plexapi.server import PlexServer

            self._server_obj = PlexServer(
                self._base_url, self._token, timeout=self._timeout
            )
        return self._server_obj

    # -- MediaSource protocol --

    def test_connection(self) -> ServerInfo:
        s = self._server()
        return ServerInfo(
            machine_identifier=s.machineIdentifier,
            friendly_name=s.friendlyName,
            version=getattr(s, "version", None),
        )

    def list_sections(self) -> list[Section]:
        out = []
        for section in self._server().library.sections():
            if section.type in ("movie", "show"):
                out.append(
                    Section(
                        key=str(section.key),
                        title=section.title,
                        movie_count=section.totalViewSize(
                            libtype=section.type, includeCollections=False
                        ),
                        type=section.type,
                    )
                )
        return out

    def count_movies(self, section_keys: list[str]) -> int:
        server = self._server()
        total = 0
        for key in section_keys:
            section = server.library.sectionByID(int(key))
            total += section.totalViewSize(libtype=section.type, includeCollections=False)
        return total

    def fetch_movies(
        self,
        section_keys: list[str],
        updated_since: int | None,
        progress: ProgressCallback | None = None,
    ) -> Iterator[MovieRecord]:
        server = self._server()
        sections = [server.library.sectionByID(int(k)) for k in section_keys]
        total: int | None = None
        if updated_since is None:
            total = sum(
                s.totalViewSize(libtype=s.type, includeCollections=False) for s in sections
            )
        processed = 0
        for section in sections:
            libtype = "show" if section.type == "show" else "movie"
            search_kwargs: dict = dict(libtype=libtype)
            if updated_since is not None:
                search_kwargs["filters"] = {
                    "updatedAt>>": datetime.fromtimestamp(updated_since)
                }
            start = 0
            while True:
                page = section.search(
                    container_start=start,
                    container_size=PAGE_SIZE,
                    maxresults=PAGE_SIZE,
                    **search_kwargs,
                )
                for item in page:
                    yield _to_record(item, libtype)
                processed += len(page)
                if progress:
                    progress(processed, total)
                if len(page) < PAGE_SIZE:
                    break
                start += PAGE_SIZE

    def fetch_artwork(self, image_path: str, width: int, height: int) -> tuple[bytes, str]:
        resp = self._http.get(
            f"{self._base_url}/photo/:/transcode",
            params={
                "url": image_path,
                "width": width,
                "height": height,
                "minSize": 1,
                "upscale": 1,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "image/jpeg")

    def collection_memberships(self, section_keys: list[str]) -> dict[str, list[str]]:
        server = self._server()
        memberships: dict[str, list[str]] = {}
        for key in section_keys:
            section = server.library.sectionByID(int(key))
            for collection in section.collections():
                title = getattr(collection, "title", None)
                if not title:
                    continue
                try:
                    members = collection.items()
                except Exception:  # a broken collection shouldn't kill the sync
                    continue
                for member in members:
                    memberships.setdefault(str(member.ratingKey), []).append(title)
        return memberships

    def list_players(self) -> list[PlayerInfo]:
        players = []
        for client in self._server().clients():
            players.append(
                PlayerInfo(
                    id=client.machineIdentifier,
                    name=client.title,
                    product=getattr(client, "product", None),
                )
            )
        return players

    def play_on(self, item_id: str, player_id: str) -> None:
        server = self._server()
        for client in server.clients():
            if client.machineIdentifier == player_id:
                client.proxyThroughServer()
                client.playMedia(server.fetchItem(int(item_id)))
                return
        raise RuntimeError("That player is no longer visible to the Plex server.")

    def deep_link(self, item_id: str) -> DeepLink:
        mid = self._server().machineIdentifier
        key = quote(f"/library/metadata/{item_id}", safe="")
        return DeepLink(
            app_url=f"plex://preplay/?metadataKey={key}&metadataType=1&server={mid}",
            web_url=f"https://app.plex.tv/desktop/#!/server/{mid}/details?key={key}",
        )


def _epoch(value) -> int | None:
    return int(value.timestamp()) if value else None


def _to_record(movie, libtype: str = "movie") -> MovieRecord:
    # Kill plexapi's per-attribute auto-reload before touching anything —
    # otherwise a sparse attribute on a partial object triggers one HTTP
    # round-trip per item (the N+1 trap, plex-notes.md §4).
    try:
        movie._autoReload = False
    except Exception:  # pragma: no cover - defensive against plexapi changes
        pass

    is_show = libtype == "show"
    if is_show:
        # A series is "unwatched" when no episode has been played.
        view_count = getattr(movie, "viewedLeafCount", None) or 0
        seasons = getattr(movie, "childCount", None)
    else:
        view_count = getattr(movie, "viewCount", 0) or 0
        seasons = None

    imdb_id = tmdb_id = None
    for g in getattr(movie, "guids", None) or []:
        gid = getattr(g, "id", "") or ""
        if gid.startswith("imdb://"):
            imdb_id = gid.removeprefix("imdb://")
        elif gid.startswith("tmdb://"):
            tmdb_id = gid.removeprefix("tmdb://")

    duration = getattr(movie, "duration", None)
    roles = (getattr(movie, "roles", None) or [])[:5]
    audience = getattr(movie, "audienceRating", None)
    critic = getattr(movie, "rating", None)

    return MovieRecord(
        id=str(movie.ratingKey),
        title=movie.title or "Untitled",
        guid=getattr(movie, "guid", None),
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        year=getattr(movie, "year", None),
        tagline=getattr(movie, "tagline", None) or None,
        summary=getattr(movie, "summary", None) or None,
        runtime_min=round(duration / 60000) if duration else None,
        content_rating=getattr(movie, "contentRating", None),
        audience_rating=audience if audience is not None else critic,
        genres=[t.tag for t in getattr(movie, "genres", None) or [] if getattr(t, "tag", None)],
        directors=[
            t.tag for t in getattr(movie, "directors", None) or [] if getattr(t, "tag", None)
        ],
        cast=[
            {"name": r.tag, "role": getattr(r, "role", None)}
            for r in roles
            if getattr(r, "tag", None)
        ],
        collections=[
            t.tag for t in getattr(movie, "collections", None) or [] if getattr(t, "tag", None)
        ],
        thumb=getattr(movie, "thumb", None),
        art=getattr(movie, "art", None),
        view_count=view_count,
        last_viewed_at=_epoch(getattr(movie, "lastViewedAt", None)),
        added_at=_epoch(getattr(movie, "addedAt", None)),
        updated_at=_epoch(getattr(movie, "updatedAt", None)),
        media_type="show" if is_show else "movie",
        seasons=seasons,
    )
