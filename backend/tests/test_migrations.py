from decide import db, migrations


def test_migration_ladder_applies_once(dbenv):
    conn = db.connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(migrations.MIGRATIONS)

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "config",
        "items",
        "sessions",
        "participants",
        "swipes",
        "matches",
        "art_cache",
    } <= tables

    # Re-applying is a no-op, not an error.
    assert migrations.apply() == version


def test_wal_mode(dbenv):
    mode = db.connect().execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
