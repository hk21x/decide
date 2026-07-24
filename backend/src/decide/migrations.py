"""PRAGMA user_version migration ladder.

MIGRATIONS[i] moves the schema from user_version i to i+1. Never edit an
entry that has shipped — append a new one.
"""

from __future__ import annotations

from importlib import resources

from . import db

MIGRATIONS: list[str] = [
    resources.files(__package__).joinpath("schema.sql").read_text(),
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
