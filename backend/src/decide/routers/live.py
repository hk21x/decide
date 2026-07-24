"""WS /api/sessions/{id}/live — server-to-client notifications only.

Cookie-authenticated at the handshake. Accept-then-close(4401) on failure so
browser clients reliably observe the close code. A 30 s idle ping keeps
reverse proxies and phone radios from reaping the socket.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import db, security

log = logging.getLogger(__name__)

router = APIRouter()

IDLE_PING_S = 30


@router.websocket("/api/sessions/{session_id}/live")
async def live(websocket: WebSocket, session_id: str) -> None:
    participant_id = security.verify_participant(
        websocket.cookies.get(security.COOKIE_NAME)
    )
    authorised = False
    if participant_id:
        row = await db.run(
            lambda: db.connect()
            .execute(
                "SELECT 1 FROM participants WHERE id = ? AND session_id = ?",
                (participant_id, session_id),
            )
            .fetchone()
        )
        authorised = row is not None

    await websocket.accept()
    if not authorised:
        await websocket.close(code=4401)
        return

    manager = websocket.app.state.events
    await manager.connect(session_id, websocket)
    try:
        while True:
            try:
                # Inbound frames are ignored (except keeping the connection
                # alive); this receive doubles as disconnect detection.
                await asyncio.wait_for(websocket.receive_text(), timeout=IDLE_PING_S)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(session_id, websocket)
