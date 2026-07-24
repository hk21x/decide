"""PRAGMA user_version migration ladder.

MIGRATIONS[i] moves the schema from user_version i to i+1. Never edit an
entry that has shipped — append a new one.
"""

from __future__ import annotations

from importlib import resources

from . import db

# v2: the stub album (snapshots that outlive session purge), per-item
# collection tags for collection decks, and the Final Round crown.
_V2 = """
ALTER TABLE items ADD COLUMN collections_json TEXT;
ALTER TABLE sessions ADD COLUMN crowned_item_id TEXT;
CREATE TABLE album (
    session_id     TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    title          TEXT NOT NULL,
    year           INTEGER,
    runtime_min    INTEGER,
    content_rating TEXT,
    names_json     TEXT NOT NULL,
    matched_at     INTEGER NOT NULL,
    saved_at       INTEGER NOT NULL,
    crowned        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, item_id)
);
"""

MIGRATIONS: list[str] = [
    resources.files(__package__).joinpath("schema.sql").read_text(),
    _V2,
]


def apply() -> int:
    """Apply outstanding migrations. Returns the resulting user_version."""
    conn = db.connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, script in enumerate(MIGRATIONS, start=1):
        if version < target:
            conn.executescript(script)  # commits any open transaction
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
            version = target
    return version
