"""Deck building (brief §5).

Pipeline order is fixed: usable items -> filters -> dedupe by guid ->
seeded shuffle -> truncate. Fewer than 10 survivors is an error that names
the responsible filter — never a silently short deck.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3

from .. import db
from ..models import DeckFilters

MIN_DECK = 10

# Certificate ranks, built from the formats observed in a real library
# (gb/-prefixed BBFC, bare US MPAA, TV ratings, legacy A/AA/X). Higher rank =
# more restrictive. Unknown or missing certificates are EXCLUDED whenever a
# ceiling is set: unrated content must not slip into a family deck.
_CERT_RANKS: dict[str, int] = {
    "U": 0, "G": 0, "TV-G": 0, "TV-Y": 0,
    "PG": 1, "TV-PG": 1, "A": 1,
    "12": 2, "12A": 2, "PG-13": 2,
    "15": 3, "AA": 3, "TV-14": 3,
    "18": 4, "R": 4, "X": 4, "NC-17": 4, "TV-MA": 4, "R18": 4,
}

CEILING_OPTIONS = ["U", "PG", "12A", "15", "18"]
_CEILING_RANKS = {"U": 0, "PG": 1, "12A": 2, "15": 3, "18": 4}

_FILTER_LABELS = {
    "unwatched_only": "the unwatched-only filter",
    "genres": "the genre filter",
    "year_range": "the decade filter",
    "max_runtime": "the runtime limit",
    "min_rating": "the minimum rating",
    "certificate": "the certificate ceiling",
}


def cert_rank(raw: str | None) -> int | None:
    if not raw:
        return None
    value = raw.strip().upper()
    if "/" in value:  # country-prefixed, e.g. gb/15
        value = value.rsplit("/", 1)[1]
    return _CERT_RANKS.get(value)


class DeckTooSmall(Exception):
    def __init__(self, count: int, culprit: str | None, would_yield: int | None):
        self.count = count
        self.culprit = culprit
        self.would_yield = would_yield
        if culprit:
            label = _FILTER_LABELS[culprit]
            self.message = (
                f"Only {count} film{'s' if count != 1 else ''} match those filters. "
                f"Removing {label} would give {would_yield}."
            )
        else:
            self.message = (
                f"Only {count} usable film{'s' if count != 1 else ''} in the library — "
                "not enough for a deck."
            )
        super().__init__(self.message)


def _load_candidates(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, guid, imdb_id, tmdb_id, year, runtime_min, content_rating, "
        "audience_rating, genres_json, view_count FROM items "
        "WHERE unusable = 0 ORDER BY id"
    ).fetchall()


def _passes(row: sqlite3.Row, f: DeckFilters) -> bool:
    if f.unwatched_only and (row["view_count"] or 0) > 0:
        return False
    if f.genres:
        item_genres = set(json.loads(row["genres_json"] or "[]"))
        if not item_genres.intersection(f.genres):
            return False
    if f.year_min is not None or f.year_max is not None:
        year = row["year"]
        if year is None:
            return False
        if f.year_min is not None and year < f.year_min:
            return False
        if f.year_max is not None and year > f.year_max:
            return False
    if f.max_runtime is not None:
        runtime = row["runtime_min"]
        if runtime is None or runtime > f.max_runtime:
            return False
    if f.min_rating is not None:
        rating = row["audience_rating"]
        if rating is None or rating < f.min_rating:
            return False
    if f.certificate is not None:
        rank = cert_rank(row["content_rating"])
        if rank is None or rank > _CEILING_RANKS[f.certificate]:
            return False
    return True


def _dedupe(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """Dedupe key preference: imdb id, then tmdb id, then raw guid, then id."""
    seen: set[str] = set()
    out = []
    for row in rows:
        key = (
            f"imdb:{row['imdb_id']}"
            if row["imdb_id"]
            else f"tmdb:{row['tmdb_id']}"
            if row["tmdb_id"]
            else f"guid:{row['guid']}"
            if row["guid"]
            else f"id:{row['id']}"
        )
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def _survivors(conn: sqlite3.Connection, filters: DeckFilters) -> list[sqlite3.Row]:
    return _dedupe([r for r in _load_candidates(conn) if _passes(r, filters)])


def _relaxations(f: DeckFilters) -> list[tuple[str, DeckFilters]]:
    out: list[tuple[str, DeckFilters]] = []
    if f.unwatched_only:
        out.append(("unwatched_only", f.model_copy(update={"unwatched_only": False})))
    if f.genres:
        out.append(("genres", f.model_copy(update={"genres": []})))
    if f.year_min is not None or f.year_max is not None:
        out.append(("year_range", f.model_copy(update={"year_min": None, "year_max": None})))
    if f.max_runtime is not None:
        out.append(("max_runtime", f.model_copy(update={"max_runtime": None})))
    if f.min_rating is not None:
        out.append(("min_rating", f.model_copy(update={"min_rating": None})))
    if f.certificate is not None:
        out.append(("certificate", f.model_copy(update={"certificate": None})))
    return out


def preview_count(filters: DeckFilters) -> int:
    """Films the deck would draw from (post-filter, post-dedupe). Blocking."""
    return len(_survivors(db.connect(), filters))


def build_deck(session_id: str, filters: DeckFilters, size: int) -> list[str]:
    """Return the frozen, ordered list of item ids. Blocking.

    Raises DeckTooSmall (<10 survivors), naming the single filter whose
    removal would recover the most films.
    """
    conn = db.connect()
    survivors = _survivors(conn, filters)
    if len(survivors) < MIN_DECK:
        culprit = None
        best_yield = None
        for name, relaxed in _relaxations(filters):
            yielded = len(_survivors(conn, relaxed))
            if best_yield is None or yielded > best_yield:
                culprit, best_yield = name, yielded
        raise DeckTooSmall(len(survivors), culprit, best_yield)

    ids = [row["id"] for row in survivors]
    seed = int.from_bytes(hashlib.sha256(session_id.encode()).digest()[:8], "big")
    random.Random(seed).shuffle(ids)
    return ids[:size]
