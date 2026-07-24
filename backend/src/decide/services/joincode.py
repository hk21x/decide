"""Join codes: 6 characters, Crockford base32 (no I, L, O, U)."""

from __future__ import annotations

import secrets
import sqlite3

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 6

# Forgiving lookups: what people type for glyphs the alphabet excludes.
_CONFUSABLES = str.maketrans({"I": "1", "L": "1", "O": "0", "U": "V"})


def generate() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def normalise(raw: str) -> str:
    return raw.strip().upper().translate(_CONFUSABLES)


def allocate(conn: sqlite3.Connection, attempts: int = 20) -> str:
    """Generate a code not already held by a session. 32^6 ≈ 1e9 codes, so
    collisions are vanishingly rare — but check anyway."""
    for _ in range(attempts):
        code = generate()
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE join_code = ?", (code,)
        ).fetchone()
        if row is None:
            return code
    raise RuntimeError("could not allocate a unique join code")
