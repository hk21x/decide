import time

import pytest
from conftest import make_movie, seed_items

from decide import db
from decide.models import DeckFilters
from decide.services import deck


def test_cert_rank_handles_real_formats():
    assert deck.cert_rank("gb/15") == 3
    assert deck.cert_rank("gb/12A") == 2
    assert deck.cert_rank("PG-13") == 2
    assert deck.cert_rank("R") == 4
    assert deck.cert_rank("gb/U") == 0
    assert deck.cert_rank("gb/A") == 1  # legacy UK cert
    assert deck.cert_rank("gb/X") == 4
    assert deck.cert_rank("TV-MA") == 4
    assert deck.cert_rank("Not Rated") is None
    assert deck.cert_rank("") is None
    assert deck.cert_rank(None) is None


def _seed_variety(count: int = 40) -> None:
    movies = []
    for i in range(1, count + 1):
        movies.append(
            make_movie(
                i,
                view_count=1 if i % 4 == 0 else 0,  # every 4th watched
                genres=["Comedy"] if i % 2 == 0 else ["Drama"],
                year=1980 + (i % 5) * 10,  # 1980..2020
                runtime_min=80 + (i % 3) * 40,  # 80 / 120 / 160
                audience_rating=5.0 + (i % 5),  # 5..9
                content_rating="gb/15" if i % 3 else "gb/U",
            )
        )
    seed_items(movies)


def test_filters_each_dimension(dbenv):
    _seed_variety()
    base = DeckFilters(unwatched_only=False)
    total = deck.preview_count(base)
    assert total == 40

    assert deck.preview_count(DeckFilters(unwatched_only=True)) == 30
    assert deck.preview_count(DeckFilters(unwatched_only=False, genres=["Comedy"])) == 20
    assert (
        deck.preview_count(DeckFilters(unwatched_only=False, year_min=2000, year_max=2009))
        == 8
    )
    assert deck.preview_count(DeckFilters(unwatched_only=False, max_runtime=90)) < total
    assert deck.preview_count(DeckFilters(unwatched_only=False, min_rating=8)) < total
    # Ceiling U: only the gb/U third qualify; gb/15 excluded.
    u_count = deck.preview_count(DeckFilters(unwatched_only=False, certificate="U"))
    assert 0 < u_count < total
    assert deck.preview_count(DeckFilters(unwatched_only=False, certificate="18")) == total


def test_unknown_cert_excluded_when_ceiling_set(dbenv):
    seed_items(
        [
            make_movie(1, content_rating="gb/PG"),
            make_movie(2, content_rating=None),
            make_movie(3, content_rating="Not Rated"),
        ]
    )
    assert deck.preview_count(DeckFilters(certificate="18")) == 1
    assert deck.preview_count(DeckFilters()) == 3


def test_dedupe_prefers_imdb(dbenv):
    seed_items(
        [
            make_movie(1, imdb_id="tt0000111"),
            make_movie(2, imdb_id="tt0000111"),  # same film, different rating key
            make_movie(3, imdb_id=None, tmdb_id="900"),
            make_movie(4, imdb_id=None, tmdb_id="900"),
            make_movie(5, imdb_id=None, tmdb_id=None, guid="plex://movie/aaa"),
        ]
    )
    assert deck.preview_count(DeckFilters()) == 3


def test_shuffle_is_seeded_and_truncated(dbenv):
    seed_items([make_movie(i) for i in range(1, 41)])
    filters = DeckFilters()
    deck_a = deck.build_deck("session-abc", filters, 20)
    deck_b = deck.build_deck("session-abc", filters, 20)
    deck_c = deck.build_deck("session-xyz", filters, 20)
    assert deck_a == deck_b
    assert len(deck_a) == 20
    assert deck_a != deck_c  # different session, different order
    assert set(deck_a) <= {str(i) for i in range(1, 41)}


def test_too_small_names_the_culprit(dbenv):
    # 8 short comedies + 30 long dramas: runtime filter is the bottleneck.
    movies = [make_movie(i, runtime_min=85, genres=["Comedy"]) for i in range(1, 9)]
    movies += [make_movie(i, runtime_min=150, genres=["Comedy"]) for i in range(9, 39)]
    seed_items(movies)
    with pytest.raises(deck.DeckTooSmall) as excinfo:
        deck.build_deck("s", DeckFilters(max_runtime=90), 30)
    err = excinfo.value
    assert err.count == 8
    assert err.culprit == "max_runtime"
    assert err.would_yield == 38
    assert "runtime limit" in err.message
    assert "38" in err.message


def test_too_small_with_no_filters(dbenv):
    seed_items([make_movie(i) for i in range(1, 5)])
    with pytest.raises(deck.DeckTooSmall) as excinfo:
        deck.build_deck("s", DeckFilters(unwatched_only=False), 30)
    assert excinfo.value.culprit is None


def test_deck_build_under_200ms_with_5000_items(dbenv):
    conn = db.connect()
    rows = [
        (
            str(i),
            f"plex://movie/{i}",
            f"tt{i:07d}" if i % 10 else None,
            str(i),
            f"Film {i}",
            1980 + (i % 45),
            None,
            f"Synopsis {i}",
            80 + (i % 100),
            "gb/15",
            5.0 + (i % 50) / 10,
            '["Drama"]',
            '["Someone"]',
            "[]",
            f"/library/metadata/{i}/thumb/1",
            None,
            0,
            None,
            1700000000,
            1700000000,
            0,
            1,
        )
        for i in range(1, 5001)
    ]
    conn.executemany(
        "INSERT INTO items (id, guid, imdb_id, tmdb_id, title, year, tagline, summary, "
        "runtime_min, content_rating, audience_rating, genres_json, directors_json, "
        "cast_json, thumb, art, view_count, last_viewed_at, added_at, updated_at, "
        "unusable, synced_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()

    deck.build_deck("warmup", DeckFilters(), 30)  # warm the page cache
    start = time.perf_counter()
    result = deck.build_deck("timed-session", DeckFilters(max_runtime=120, min_rating=6), 30)
    elapsed = time.perf_counter() - start
    assert len(result) == 30
    assert elapsed < 0.2, f"deck build took {elapsed * 1000:.0f}ms"
