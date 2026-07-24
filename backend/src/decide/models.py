"""Pydantic request/response models.

C1 discipline: no model in this module has a field that could carry the Plex
token. Tokens are accepted in one request body (the paste-a-token escape
hatch) and never returned.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SetupStatus(BaseModel):
    stage: str  # unconfigured | needs_server | needs_sections | ready
    server_name: str | None = None
    machine_id: str | None = None
    sections: list[str] | None = None


class PinStart(BaseModel):
    id: str
    code: str
    link_url: str = "https://plex.tv/link"


class ServerEntry(BaseModel):
    name: str
    machine_id: str
    owned: bool


class PinPoll(BaseModel):
    authenticated: bool
    expired: bool = False
    servers: list[ServerEntry] | None = None


class SectionEntry(BaseModel):
    key: str
    title: str
    movie_count: int


class SetupServerRequest(BaseModel):
    machine_id: str | None = None
    url: str | None = None
    token: str | None = None  # paste-a-token escape hatch; never echoed back
    sections: list[str] | None = None


class SetupServerResponse(BaseModel):
    stage: str
    server_name: str | None = None
    machine_id: str | None = None
    available_sections: list[SectionEntry] | None = None


class SyncRequest(BaseModel):
    full: bool = False


class SyncStarted(BaseModel):
    started: bool


class LibraryStatus(BaseModel):
    stage: str
    state: str  # idle | syncing
    kind: str | None = None
    processed: int = 0
    total: int | None = None
    error: str | None = None
    item_count: int = 0
    unusable_count: int = 0
    last_synced_at: int | None = None
    sections: list[str] | None = None


class Health(BaseModel):
    status: str = Field(default="ok")


# ---- deck + sessions (M2) ----

from typing import Literal  # noqa: E402


class DeckFilters(BaseModel):
    unwatched_only: bool = True
    genres: list[str] = Field(default_factory=list)
    year_min: int | None = Field(default=None, ge=1880, le=2100)
    year_max: int | None = Field(default=None, ge=1880, le=2100)
    max_runtime: int | None = Field(default=None, ge=30, le=600)
    min_rating: float | None = Field(default=None, ge=0, le=10)
    certificate: Literal["U", "PG", "12A", "15", "18"] | None = None
    collection: str | None = Field(default=None, max_length=200)


class LibraryFilters(BaseModel):
    genres: list[str]
    decades: list[int]
    certificates: list[str]
    collections: list[str] = Field(default_factory=list)


class PreviewCount(BaseModel):
    count: int


class CreateSessionRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)
    filters: DeckFilters = Field(default_factory=DeckFilters)
    deck_size: Literal[20, 30, 50] = 30


class CreateSessionResponse(BaseModel):
    id: str
    join_code: str
    deck_size: int
    participant_id: str
    expires_at: int


class ParticipantEntry(BaseModel):
    id: str
    display_name: str
    joined_at: int


class SessionSummary(BaseModel):
    id: str
    join_code: str
    state: str
    deck_size: int
    created_at: int
    expires_at: int
    participants: list[ParticipantEntry]
    filters: DeckFilters
    crowned_item_id: str | None = None


class JoinRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class JoinResponse(BaseModel):
    participant_id: str
    session: SessionSummary


class DeckItem(BaseModel):
    id: str
    title: str
    year: int | None = None
    tagline: str | None = None
    summary: str | None = None
    runtime_min: int | None = None
    content_rating: str | None = None
    audience_rating: float | None = None
    genres: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    cast: list[dict] = Field(default_factory=list)
    has_poster: bool = False
    has_backdrop: bool = False


class DeckResponse(BaseModel):
    session_id: str
    deck_size: int
    items: list[DeckItem]


class SwipeIn(BaseModel):
    item_id: str
    direction: Literal[0, 1]  # 1 = Tonight, 0 = Not tonight


class SwipeBatch(BaseModel):
    swipes: list[SwipeIn] = Field(min_length=1, max_length=60)


class SwipeResult(BaseModel):
    accepted: int
    new_matches: list[str] = Field(default_factory=list)
    removed_matches: list[str] = Field(default_factory=list)


class MatchEntry(BaseModel):
    item: DeckItem
    matched_at: int
    right_count: int
    participant_count: int
    right_names: list[str] = Field(default_factory=list)  # for the ticket stub


class MatchesResponse(BaseModel):
    session_id: str
    matches: list[MatchEntry]


class ProgressEntry(BaseModel):
    participant_id: str
    display_name: str
    swiped: int
    total: int


class ProgressResponse(BaseModel):
    session_id: str
    state: str
    deck_size: int
    participants: list[ProgressEntry]
    match_count: int
    all_complete: bool


class PairStat(BaseModel):
    a_id: str
    a_name: str
    b_id: str
    b_name: str
    both_swiped: int
    agreed: int
    both_right: int
    pct: int  # agreed / both_swiped, rounded


class SessionStats(BaseModel):
    session_id: str
    deck_size: int
    pairs: list[PairStat]


class CrownRequest(BaseModel):
    item_id: str


class CrownResponse(BaseModel):
    crowned_item_id: str


class AlbumSaveRequest(BaseModel):
    item_id: str
    crowned: bool = False


class AlbumEntry(BaseModel):
    session_id: str
    item_id: str
    title: str
    year: int | None = None
    runtime_min: int | None = None
    content_rating: str | None = None
    names: list[str]
    matched_at: int
    saved_at: int
    crowned: bool


class AlbumResponse(BaseModel):
    entries: list[AlbumEntry]


class PlayerEntry(BaseModel):
    id: str
    name: str
    product: str | None = None


class PlayersResponse(BaseModel):
    players: list[PlayerEntry]


class PlayRequest(BaseModel):
    item_id: str
    player_id: str
