"""MediaSource protocol (constraint C3).

Everything Matinee needs from a media server, expressed without Plex types so
a JellyfinSource can drop in later. All methods are synchronous — callers wrap
them in asyncio.to_thread. Auth flows (PIN login, account discovery) are
deliberately NOT part of the protocol; they differ per backend and live as
module functions next to each implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass
class ServerInfo:
    machine_identifier: str
    friendly_name: str
    version: str | None = None


@dataclass
class Section:
    key: str
    title: str
    movie_count: int


@dataclass
class DeepLink:
    app_url: str
    web_url: str


@dataclass
class MovieRecord:
    """Mirrors the items table. One row per film."""

    id: str
    title: str
    guid: str | None = None
    imdb_id: str | None = None
    tmdb_id: str | None = None
    year: int | None = None
    tagline: str | None = None
    summary: str | None = None
    runtime_min: int | None = None
    content_rating: str | None = None
    audience_rating: float | None = None
    genres: list[str] = field(default_factory=list)
    directors: list[str] = field(default_factory=list)
    cast: list[dict] = field(default_factory=list)
    thumb: str | None = None
    art: str | None = None
    view_count: int = 0
    last_viewed_at: int | None = None
    added_at: int | None = None
    updated_at: int | None = None


ProgressCallback = Callable[[int, int | None], None]  # (processed, total-or-unknown)


class MediaSource(Protocol):
    def test_connection(self) -> ServerInfo: ...

    def list_movie_sections(self) -> list[Section]: ...

    def fetch_movies(
        self,
        section_keys: list[str],
        updated_since: int | None,
        progress: ProgressCallback | None = None,
    ) -> Iterator[MovieRecord]:
        """Yield movies from the given sections.

        updated_since (epoch seconds) limits to items changed after that
        moment; None means everything.
        """
        ...

    def count_movies(self, section_keys: list[str]) -> int:
        """Cheap total across sections — used to detect deletions after an
        incremental sync (incremental filters cannot see removals)."""
        ...

    def fetch_artwork(
        self, image_path: str, width: int, height: int
    ) -> tuple[bytes, str]:
        """Return (image bytes, content type) for a stored thumb/art path,
        resized server-side to cover width x height."""
        ...

    def deep_link(self, item_id: str) -> DeepLink: ...


ArtKind = Literal["poster", "backdrop"]
