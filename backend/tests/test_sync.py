import time

from conftest import FakeSource, make_movie

from decide import config as cfg
from decide import db
from decide.services.sync import run_sync_blocking


def _counts():
    conn = db.connect()
    (total,) = conn.execute("SELECT COUNT(*) FROM items").fetchone()
    (unusable,) = conn.execute("SELECT COUNT(*) FROM items WHERE unusable = 1").fetchone()
    return total, unusable


def test_full_sync_stores_and_flags_unusable(dbenv):
    movies = [
        make_movie(1),
        make_movie(2, thumb=None, summary=None),  # no poster AND no summary
        make_movie(3, thumb=None),  # summary present -> still usable
    ]
    outcome = run_sync_blocking(FakeSource(movies), ["1"], full=True)
    assert outcome.kind == "full"
    assert outcome.processed == 3

    total, unusable = _counts()
    assert (total, unusable) == (3, 1)

    row = db.connect().execute("SELECT * FROM items WHERE id = '1'").fetchone()
    assert row["title"] == "Film 1"
    assert row["imdb_id"] == "tt0000001"
    assert row["runtime_min"] == 91
    assert '"Drama"' in row["genres_json"]


def test_full_sync_is_idempotent(dbenv):
    movies = [make_movie(i) for i in range(1, 6)]
    run_sync_blocking(FakeSource(movies), ["1"], full=True)
    run_sync_blocking(FakeSource(movies), ["1"], full=True)
    assert _counts()[0] == 5


def test_full_sync_deletes_removed_items(dbenv):
    run_sync_blocking(FakeSource([make_movie(i) for i in range(1, 4)]), ["1"], full=True)
    outcome = run_sync_blocking(
        FakeSource([make_movie(1), make_movie(3)]), ["1"], full=True
    )
    assert outcome.deleted == 1
    assert _counts()[0] == 2


def test_incremental_only_touches_updated(dbenv):
    movies = [make_movie(i) for i in range(1, 4)]
    run_sync_blocking(FakeSource(movies), ["1"], full=True)

    fresh = int(time.time()) + 60
    changed = make_movie(2, title="Film 2 (director's cut)", updated_at=fresh)
    source = FakeSource([movies[0], changed, movies[2]])
    outcome = run_sync_blocking(source, ["1"], full=False)

    assert outcome.kind == "incremental"
    assert outcome.processed == 1
    assert outcome.needs_full is False
    row = db.connect().execute("SELECT title FROM items WHERE id = '2'").fetchone()
    assert row["title"] == "Film 2 (director's cut)"
    assert _counts()[0] == 3


def test_incremental_detects_removals(dbenv):
    movies = [make_movie(i) for i in range(1, 4)]
    run_sync_blocking(FakeSource(movies), ["1"], full=True)
    outcome = run_sync_blocking(FakeSource(movies[:2]), ["1"], full=False)
    assert outcome.needs_full is True


def test_incremental_without_prior_sync_promotes_to_full(dbenv):
    outcome = run_sync_blocking(FakeSource([make_movie(1)]), ["1"], full=False)
    assert outcome.kind == "full"
    assert _counts()[0] == 1


def test_progress_callback_receives_totals(dbenv):
    seen: list[tuple[int, int | None]] = []
    run_sync_blocking(
        FakeSource([make_movie(i) for i in range(1, 8)]),
        ["1"],
        full=True,
        progress_cb=lambda processed, total: seen.append((processed, total)),
    )
    assert seen and seen[-1] == (7, 7)
    assert cfg.get_value("last_sync_epoch") is not None
