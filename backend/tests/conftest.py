from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from decide import config as cfg
from decide import db, migrations, security
from decide.config import Settings
from decide.main import create_app
from decide.sources.base import DeepLink, MovieRecord, Section, ServerInfo

_BASE_EPOCH = 1_700_000_000


def make_movie(i: int, **overrides) -> MovieRecord:
    base = MovieRecord(
        id=str(i),
        title=f"Film {i}",
        guid=f"plex://movie/{i:024x}",
        imdb_id=f"tt{i:07d}",
        tmdb_id=str(1000 + i),
        year=1990 + (i % 30),
        tagline=f"Tagline {i}",
        summary=f"Synopsis for film {i}.",
        runtime_min=90 + i,
        content_rating="15",
        audience_rating=6.0 + (i % 4),
        genres=["Drama", "Thriller"],
        directors=[f"Director {i}"],
        cast=[{"name": f"Actor {i}", "role": "Lead"}],
        thumb=f"/library/metadata/{i}/thumb/1",
        art=f"/library/metadata/{i}/art/1",
        view_count=0,
        last_viewed_at=None,
        added_at=_BASE_EPOCH + i,
        updated_at=_BASE_EPOCH + i,
    )
    return replace(base, **overrides)


class FakeSource:
    """MediaSource over an in-memory list — the test double for PlexSource."""

    def __init__(self, movies: list[MovieRecord]):
        self.movies = list(movies)

    def test_connection(self) -> ServerInfo:
        return ServerInfo("FAKEMACHINE0123", "Fake Server", "1.0")

    def list_movie_sections(self) -> list[Section]:
        return [Section("1", "Films", len(self.movies))]

    def count_movies(self, section_keys: list[str]) -> int:
        return len(self.movies)

    def fetch_movies(self, section_keys, updated_since, progress=None):
        sent = 0
        for movie in self.movies:
            if updated_since is not None and (movie.updated_at or 0) <= updated_since:
                continue
            sent += 1
            yield movie
        if progress:
            progress(sent, len(self.movies) if updated_since is None else None)

    def fetch_artwork(self, image_path, width, height):
        return b"\xff\xd8\xff-fake-jpeg", "image/jpeg"

    def deep_link(self, item_id):
        return DeepLink(
            app_url=f"plex://preplay/?metadataKey=%2Flibrary%2Fmetadata%2F{item_id}"
            "&metadataType=1&server=FAKEMACHINE0123",
            web_url=f"https://app.plex.tv/desktop/#!/server/FAKEMACHINE0123/details"
            f"?key=%2Flibrary%2Fmetadata%2F{item_id}",
        )


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", enable_jobs=False)


@pytest.fixture
def dbenv(settings) -> Settings:
    """Configured DB + config + secret, no HTTP app. For service-level tests."""
    cfg.init(settings)
    db.configure(settings.data_dir / "decide.db")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    migrations.apply()
    security.bootstrap()
    return settings


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, app


def mark_ready(token: str = "test-token-0123456789") -> None:
    """Write config rows that make setup_stage() == ready."""
    cfg.set_value("plex_token", token)
    cfg.set_value("plex_url", "http://fake-pms:32400")
    cfg.set_value("plex_sections", json.dumps(["1"]))


def seed_items(movies: list[MovieRecord]) -> None:
    """Insert MovieRecords through the real sync path."""
    from decide.services.sync import run_sync_blocking

    run_sync_blocking(FakeSource(movies), ["1"], full=True)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from decide.ratelimit import code_lookup_limiter

    code_lookup_limiter.reset()
    yield
    code_lookup_limiter.reset()
