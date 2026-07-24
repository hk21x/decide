"""Sessions: create, lookup by code, join, deck, swipes, matches, progress.

Participant identity is a signed httpOnly cookie scoped to this session's
API path, so one browser can hold identities in several sessions at once.
Swipes arrive in batches; REST is the source of truth (the M4 WebSocket is
notification-only).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from .. import config, db, security
from ..models import (
    CreateSessionRequest,
    CreateSessionResponse,
    DeckFilters,
    DeckItem,
    DeckResponse,
    JoinRequest,
    JoinResponse,
    MatchEntry,
    MatchesResponse,
    ParticipantEntry,
    ProgressEntry,
    ProgressResponse,
    SessionSummary,
    SwipeBatch,
    SwipeResult,
)
from ..ratelimit import code_lookup_limiter
from ..services import deck as deck_service
from ..services import joincode
from ..services import matches as match_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

SESSION_TTL_S = 48 * 3600
MAX_PARTICIPANTS = 4
COOKIE_MAX_AGE_S = 7 * 86400


# ---------------------------------------------------------------- helpers

def _load_session(session_id: str) -> sqlite3.Row:
    row = db.connect().execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No such session.")
    if row["state"] == "expired" or row["expires_at"] < int(time.time()):
        raise HTTPException(status_code=410, detail="This session has closed.")
    return row


def _participants(session_id: str) -> list[sqlite3.Row]:
    return db.connect().execute(
        "SELECT * FROM participants WHERE session_id = ? ORDER BY joined_at",
        (session_id,),
    ).fetchall()


def _summary(session: sqlite3.Row) -> SessionSummary:
    return SessionSummary(
        id=session["id"],
        join_code=session["join_code"],
        state=session["state"],
        deck_size=len(json.loads(session["deck_json"])),
        created_at=session["created_at"],
        expires_at=session["expires_at"],
        participants=[
            ParticipantEntry(
                id=p["id"], display_name=p["display_name"], joined_at=p["joined_at"]
            )
            for p in _participants(session["id"])
        ],
        filters=DeckFilters(**json.loads(session["filters_json"])),
    )


async def _current_participant(session_id: str, request: Request) -> sqlite3.Row:
    """The session row is checked first (404/410 beat 401)."""
    await db.run(_load_session, session_id)
    participant_id = security.verify_participant(
        request.cookies.get(security.COOKIE_NAME)
    )
    if participant_id:
        row = await db.run(
            lambda: db.connect()
            .execute(
                "SELECT * FROM participants WHERE id = ? AND session_id = ?",
                (participant_id, session_id),
            )
            .fetchone()
        )
        if row is not None:
            return row
    raise HTTPException(status_code=401, detail="Join this session before swiping.")


def _set_participant_cookie(response: Response, session_id: str, participant_id: str) -> None:
    response.set_cookie(
        key=security.COOKIE_NAME,
        value=security.sign_participant(participant_id),
        httponly=True,
        samesite="lax",
        path=f"/api/sessions/{session_id}",
        max_age=COOKIE_MAX_AGE_S,
    )


def _row_to_deck_item(row: sqlite3.Row) -> DeckItem:
    return DeckItem(
        id=row["id"],
        title=row["title"],
        year=row["year"],
        tagline=row["tagline"],
        summary=row["summary"],
        runtime_min=row["runtime_min"],
        content_rating=row["content_rating"],
        audience_rating=row["audience_rating"],
        genres=json.loads(row["genres_json"] or "[]"),
        directors=json.loads(row["directors_json"] or "[]"),
        cast=json.loads(row["cast_json"] or "[]"),
        has_poster=bool(row["thumb"]),
        has_backdrop=bool(row["art"]),
    )


def _items_by_id(item_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not item_ids:
        return {}
    marks = ",".join("?" * len(item_ids))
    rows = db.connect().execute(
        f"SELECT * FROM items WHERE id IN ({marks})", item_ids
    ).fetchall()
    return {r["id"]: r for r in rows}


def _swipe_stats(session_id: str, participant_id: str) -> tuple[int, int, bool, list]:
    """(my swiped count, deck size, everyone finished, right-swiper rows fn)"""
    conn = db.connect()
    session = conn.execute(
        "SELECT deck_json FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    deck_size = len(json.loads(session["deck_json"])) if session else 0
    (swiped,) = conn.execute(
        "SELECT COUNT(*) FROM swipes WHERE session_id = ? AND participant_id = ?",
        (session_id, participant_id),
    ).fetchone()
    counts = conn.execute(
        "SELECT p.id, COUNT(s.item_id) AS n FROM participants p "
        "LEFT JOIN swipes s ON s.session_id = p.session_id AND s.participant_id = p.id "
        "WHERE p.session_id = ? GROUP BY p.id",
        (session_id,),
    ).fetchall()
    all_complete = bool(counts) and all(r["n"] >= deck_size for r in counts)
    return swiped, deck_size, all_complete, counts


def _right_swipers(session_id: str, item_id: str) -> list[sqlite3.Row]:
    return db.connect().execute(
        "SELECT p.id, p.display_name FROM swipes s "
        "JOIN participants p ON p.id = s.participant_id "
        "WHERE s.session_id = ? AND s.item_id = ? AND s.direction = 1 "
        "ORDER BY p.joined_at",
        (session_id, item_id),
    ).fetchall()


async def _broadcast_swipe_effects(request: Request, session_id: str, participant, outcome):
    """Progress, match/unmatch and complete events after any swipe write."""
    events = request.app.state.events
    swiped, deck_size, all_complete, _ = await db.run(
        _swipe_stats, session_id, participant["id"]
    )
    await events.broadcast(
        session_id,
        {
            "type": "progress",
            "participant_id": participant["id"],
            "display_name": participant["display_name"],
            "swiped": swiped,
            "total": deck_size,
        },
    )
    for item_id in outcome.new_matches:
        swipers = await db.run(_right_swipers, session_id, item_id)
        await events.broadcast(
            session_id,
            {
                "type": "match",
                "item_id": item_id,
                "participant_ids": [r["id"] for r in swipers],
            },
        )
    for item_id in outcome.removed_matches:
        await events.broadcast(session_id, {"type": "unmatch", "item_id": item_id})
    if all_complete:
        await events.broadcast(session_id, {"type": "complete"})


# ---------------------------------------------------------------- routes

@router.post("", response_model=CreateSessionResponse, status_code=201)
async def create_session(body: CreateSessionRequest, response: Response):
    if await db.run(config.setup_stage) != "ready":
        raise HTTPException(
            status_code=409, detail="Connect Matinee to Plex before starting a session."
        )
    session_id = uuid.uuid4().hex
    try:
        deck_ids = await db.run(
            deck_service.build_deck, session_id, body.filters, body.deck_size
        )
    except deck_service.DeckTooSmall as too_small:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "too_few_films",
                "count": too_small.count,
                "culprit": too_small.culprit,
                "would_yield": too_small.would_yield,
                "message": too_small.message,
            },
        ) from None

    host_id = str(uuid.uuid4())
    now = int(time.time())

    def _create() -> str:
        conn = db.connect()
        code = joincode.allocate(conn)
        conn.execute(
            "INSERT INTO sessions (id, join_code, host_participant_id, filters_json, "
            "deck_json, state, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                code,
                host_id,
                body.filters.model_dump_json(),
                json.dumps(deck_ids),
                "open",
                now,
                now + SESSION_TTL_S,
            ),
        )
        conn.execute(
            "INSERT INTO participants (id, session_id, display_name, joined_at) "
            "VALUES (?, ?, ?, ?)",
            (host_id, session_id, body.display_name.strip(), now),
        )
        conn.commit()
        return code

    code = await db.run(_create)
    _set_participant_cookie(response, session_id, host_id)
    return CreateSessionResponse(
        id=session_id,
        join_code=code,
        deck_size=len(deck_ids),
        participant_id=host_id,
        expires_at=now + SESSION_TTL_S,
    )


@router.get("/{code}", response_model=SessionSummary)
async def lookup_by_code(code: str, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not code_lookup_limiter.allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Wait a minute, then try again.",
            headers={"Retry-After": "60"},
        )
    normalised = joincode.normalise(code)

    def _find() -> sqlite3.Row | None:
        return db.connect().execute(
            "SELECT * FROM sessions WHERE join_code = ?", (normalised,)
        ).fetchone()

    session = await db.run(_find)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="No session with that code. Check it and try again.",
        )
    if session["state"] == "expired" or session["expires_at"] < int(time.time()):
        raise HTTPException(status_code=410, detail="This session has closed.")
    return await db.run(_summary, session)


@router.get("/{session_id}/summary", response_model=SessionSummary)
async def session_summary(session_id: str, request: Request):
    await _current_participant(session_id, request)
    session = await db.run(_load_session, session_id)
    return await db.run(_summary, session)


@router.post("/{session_id}/join", response_model=JoinResponse)
async def join_session(session_id: str, body: JoinRequest, request: Request, response: Response):
    session = await db.run(_load_session, session_id)
    participants = await db.run(_participants, session_id)
    if len(participants) >= MAX_PARTICIPANTS:
        raise HTTPException(
            status_code=409, detail="This session already has four people."
        )
    participant_id = str(uuid.uuid4())

    def _join() -> None:
        conn = db.connect()
        conn.execute(
            "INSERT INTO participants (id, session_id, display_name, joined_at) "
            "VALUES (?, ?, ?, ?)",
            (participant_id, session_id, body.display_name.strip(), int(time.time())),
        )
        conn.commit()

    await db.run(_join)
    _set_participant_cookie(response, session_id, participant_id)
    await request.app.state.events.broadcast(
        session_id,
        {
            "type": "joined",
            "participant_id": participant_id,
            "display_name": body.display_name.strip(),
        },
    )
    return JoinResponse(
        participant_id=participant_id, session=await db.run(_summary, session)
    )


@router.get("/{session_id}/deck", response_model=DeckResponse)
async def get_deck(session_id: str, request: Request):
    await _current_participant(session_id, request)
    session = await db.run(_load_session, session_id)
    deck_ids: list[str] = json.loads(session["deck_json"])
    by_id = await db.run(_items_by_id, deck_ids)
    items = [_row_to_deck_item(by_id[i]) for i in deck_ids if i in by_id]
    return DeckResponse(session_id=session_id, deck_size=len(deck_ids), items=items)


@router.post("/{session_id}/swipes", response_model=SwipeResult)
async def post_swipes(session_id: str, body: SwipeBatch, request: Request):
    participant = await _current_participant(session_id, request)
    session = await db.run(_load_session, session_id)
    deck_ids = set(json.loads(session["deck_json"]))
    unknown = [s.item_id for s in body.swipes if s.item_id not in deck_ids]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"These films aren't in this session's deck: {', '.join(unknown)}",
        )
    outcome = await db.run(
        lambda: match_service.apply_swipes(
            db.connect(),
            session_id,
            participant["id"],
            [(s.item_id, s.direction) for s in body.swipes],
        )
    )
    await _broadcast_swipe_effects(request, session_id, participant, outcome)
    return SwipeResult(
        accepted=outcome.accepted,
        new_matches=outcome.new_matches,
        removed_matches=outcome.removed_matches,
    )


@router.delete("/{session_id}/swipes/{item_id}", response_model=SwipeResult)
async def undo_swipe(session_id: str, item_id: str, request: Request):
    participant = await _current_participant(session_id, request)
    outcome = await db.run(
        lambda: match_service.undo_swipe(
            db.connect(), session_id, participant["id"], item_id
        )
    )
    await _broadcast_swipe_effects(request, session_id, participant, outcome)
    return SwipeResult(
        accepted=outcome.accepted,
        new_matches=outcome.new_matches,
        removed_matches=outcome.removed_matches,
    )


@router.get("/{session_id}/matches", response_model=MatchesResponse)
async def get_matches(session_id: str, request: Request):
    await _current_participant(session_id, request)

    def _read() -> MatchesResponse:
        conn = db.connect()
        rows = conn.execute(
            "SELECT m.item_id, m.matched_at FROM matches m "
            "WHERE m.session_id = ? ORDER BY m.matched_at DESC",
            (session_id,),
        ).fetchall()
        (participant_count,) = conn.execute(
            "SELECT COUNT(*) FROM participants WHERE session_id = ?", (session_id,)
        ).fetchone()
        by_id = _items_by_id([r["item_id"] for r in rows])
        entries = []
        for row in rows:
            item = by_id.get(row["item_id"])
            if item is None:
                continue  # film left the library mid-session
            swipers = _right_swipers(session_id, row["item_id"])
            entries.append(
                MatchEntry(
                    item=_row_to_deck_item(item),
                    matched_at=row["matched_at"],
                    right_count=len(swipers),
                    participant_count=participant_count,
                    right_names=[s["display_name"] for s in swipers],
                )
            )
        return MatchesResponse(session_id=session_id, matches=entries)

    return await db.run(_read)


@router.get("/{session_id}/progress", response_model=ProgressResponse)
async def get_progress(session_id: str, request: Request):
    await _current_participant(session_id, request)
    session = await db.run(_load_session, session_id)
    deck_size = len(json.loads(session["deck_json"]))

    def _read() -> ProgressResponse:
        conn = db.connect()
        entries = []
        complete_flags = []
        for p in _participants(session_id):
            (swiped,) = conn.execute(
                "SELECT COUNT(*) FROM swipes WHERE session_id = ? AND participant_id = ?",
                (session_id, p["id"]),
            ).fetchone()
            entries.append(
                ProgressEntry(
                    participant_id=p["id"],
                    display_name=p["display_name"],
                    swiped=swiped,
                    total=deck_size,
                )
            )
            complete_flags.append(swiped >= deck_size)
        (match_count,) = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE session_id = ?", (session_id,)
        ).fetchone()
        return ProgressResponse(
            session_id=session_id,
            state=session["state"],
            deck_size=deck_size,
            participants=entries,
            match_count=match_count,
            all_complete=bool(complete_flags) and all(complete_flags),
        )

    return await db.run(_read)
