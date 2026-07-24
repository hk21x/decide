"""WebSocket connection manager: one room per session.

Notification-only (brief §4.6) — REST is the source of truth, so a dropped
event costs nothing: clients refetch on reconnect.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._rooms.setdefault(session_id, set()).add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(session_id)
            if room:
                room.discard(websocket)
                if not room:
                    del self._rooms[session_id]

    async def broadcast(self, session_id: str, event: dict) -> None:
        async with self._lock:
            targets = list(self._rooms.get(session_id, ()))
        dead: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            await self.disconnect(session_id, websocket)
