"""Swipe application and match computation — the single code path.

Match rule (brief §4.6): a film matches when every participant who has
joined has swiped right. A later joiner never invalidates an existing match
(the UI labels it "2 of 3"). A match IS removed when one of its right-swipes
is retracted — undone, or changed to a left swipe — because the unanimity
that created it is gone.

Direction encoding: 1 = right ("Tonight"), 0 = left ("Not tonight").
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class SwipeOutcome:
    accepted: int = 0
    new_matches: list[str] = field(default_factory=list)
    removed_matches: list[str] = field(default_factory=list)


def _participant_count(conn: sqlite3.Connection, session_id: str) -> int:
    (n,) = conn.execute(
        "SELECT COUNT(*) FROM participants WHERE session_id = ?", (session_id,)
    ).fetchone()
    return n


def _right_count(conn: sqlite3.Connection, session_id: str, item_id: str) -> int:
    (n,) = conn.execute(
        "SELECT COUNT(*) FROM swipes WHERE session_id = ? AND item_id = ? AND direction = 1",
        (session_id, item_id),
    ).fetchone()
    return n


def _match_exists(conn: sqlite3.Connection, session_id: str, item_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM matches WHERE session_id = ? AND item_id = ?",
            (session_id, item_id),
        ).fetchone()
        is not None
    )


def _maybe_match(conn: sqlite3.Connection, session_id: str, item_id: str) -> bool:
    """Create a match if every current participant has swiped right."""
    participants = _participant_count(conn, session_id)
    if participants == 0 or _right_count(conn, session_id, item_id) < participants:
        return False
    cur = conn.execute(
        "INSERT OR IGNORE INTO matches (session_id, item_id, matched_at) VALUES (?, ?, ?)",
        (session_id, item_id, int(time.time())),
    )
    return cur.rowcount > 0


def _remove_match(conn: sqlite3.Connection, session_id: str, item_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM matches WHERE session_id = ? AND item_id = ?",
        (session_id, item_id),
    )
    return cur.rowcount > 0


def apply_swipes(
    conn: sqlite3.Connection,
    session_id: str,
    participant_id: str,
    swipes: list[tuple[str, int]],  # (item_id, direction)
) -> SwipeOutcome:
    """Upsert a batch of swipes and recompute matches for affected items.

    Idempotent: replaying the same batch is a no-op (composite primary key,
    ON CONFLICT DO UPDATE). Runs inside one transaction. Blocking.
    """
    outcome = SwipeOutcome()
    now = int(time.time())
    rights: list[str] = []
    retractions: list[str] = []

    for item_id, direction in swipes:
        previous = conn.execute(
            "SELECT direction FROM swipes WHERE session_id = ? AND participant_id = ? "
            "AND item_id = ?",
            (session_id, participant_id, item_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO swipes (session_id, participant_id, item_id, direction, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, participant_id, item_id) "
            "DO UPDATE SET direction = excluded.direction",
            (session_id, participant_id, item_id, direction, now),
        )
        outcome.accepted += 1
        if direction == 1:
            rights.append(item_id)
        elif previous is not None and previous["direction"] == 1:
            retractions.append(item_id)  # right -> left

    for item_id in dict.fromkeys(rights):
        if _maybe_match(conn, session_id, item_id):
            outcome.new_matches.append(item_id)
    for item_id in dict.fromkeys(retractions):
        if _remove_match(conn, session_id, item_id):
            outcome.removed_matches.append(item_id)

    conn.commit()
    return outcome


def undo_swipe(
    conn: sqlite3.Connection, session_id: str, participant_id: str, item_id: str
) -> SwipeOutcome:
    """Delete one swipe; drop the match it was part of, if any. Blocking."""
    outcome = SwipeOutcome()
    previous = conn.execute(
        "SELECT direction FROM swipes WHERE session_id = ? AND participant_id = ? "
        "AND item_id = ?",
        (session_id, participant_id, item_id),
    ).fetchone()
    if previous is None:
        conn.commit()
        return outcome

    conn.execute(
        "DELETE FROM swipes WHERE session_id = ? AND participant_id = ? AND item_id = ?",
        (session_id, participant_id, item_id),
    )
    outcome.accepted = 1
    if previous["direction"] == 1 and _remove_match(conn, session_id, item_id):
        outcome.removed_matches.append(item_id)
    conn.commit()
    return outcome
