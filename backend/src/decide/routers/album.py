"""The stub album: matched films you chose to keep.

Entries are denormalised snapshots (title, names, date) so they survive both
the 7-day session purge and library changes — you keep the ticket, not the
session.
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..models import AlbumEntry, AlbumResponse, AlbumSaveRequest
from .sessions import _current_participant, _right_swipers

router = APIRouter(prefix="/api", tags=["album"])


@router.post("/sessions/{session_id}/album", response_model=AlbumEntry)
async def save_stub(session_id: str, body: AlbumSaveRequest, request: Request):
    await _current_participant(session_id, request)

    def _save() -> AlbumEntry | None:
        conn = db.connect()
        match = conn.execute(
            "SELECT m.matched_at, i.title, i.year, i.runtime_min, i.content_rating "
            "FROM matches m JOIN items i ON i.id = m.item_id "
            "WHERE m.session_id = ? AND m.item_id = ?",
            (session_id, body.item_id),
        ).fetchone()
        if match is None:
            return None
        names = [r["display_name"] for r in _right_swipers(session_id, body.item_id)]
        now = int(time.time())
        conn.execute(
            "INSERT INTO album (session_id, item_id, title, year, runtime_min, "
            "content_rating, names_json, matched_at, saved_at, crowned) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, item_id) DO UPDATE SET "
            "crowned = MAX(album.crowned, excluded.crowned), saved_at = excluded.saved_at",
            (
                session_id,
                body.item_id,
                match["title"],
                match["year"],
                match["runtime_min"],
                match["content_rating"],
                json.dumps(names),
                match["matched_at"],
                now,
                1 if body.crowned else 0,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM album WHERE session_id = ? AND item_id = ?",
            (session_id, body.item_id),
        ).fetchone()
        return _entry(row)

    entry = await db.run(_save)
    if entry is None:
        raise HTTPException(
            status_code=400, detail="Only matched films can go in the album."
        )
    return entry


def _entry(row) -> AlbumEntry:
    return AlbumEntry(
        session_id=row["session_id"],
        item_id=row["item_id"],
        title=row["title"],
        year=row["year"],
        runtime_min=row["runtime_min"],
        content_rating=row["content_rating"],
        names=json.loads(row["names_json"]),
        matched_at=row["matched_at"],
        saved_at=row["saved_at"],
        crowned=bool(row["crowned"]),
    )


@router.get("/album", response_model=AlbumResponse)
async def list_album() -> AlbumResponse:
    def _read() -> list[AlbumEntry]:
        rows = db.connect().execute(
            "SELECT * FROM album ORDER BY saved_at DESC"
        ).fetchall()
        return [_entry(r) for r in rows]

    return AlbumResponse(entries=await db.run(_read))


@router.delete("/album/{session_id}/{item_id}", response_model=AlbumResponse)
async def remove_stub(session_id: str, item_id: str) -> AlbumResponse:
    def _delete() -> list[AlbumEntry]:
        conn = db.connect()
        conn.execute(
            "DELETE FROM album WHERE session_id = ? AND item_id = ?",
            (session_id, item_id),
        )
        conn.commit()
        rows = conn.execute("SELECT * FROM album ORDER BY saved_at DESC").fetchall()
        return [_entry(r) for r in rows]

    return AlbumResponse(entries=await db.run(_delete))
