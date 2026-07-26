"""Web Push endpoints: VAPID public key + per-session subscription."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import db
from ..models import PushSubscription, VapidKey
from ..services import push as push_service
from .sessions import _current_participant

router = APIRouter(prefix="/api", tags=["push"])


@router.get("/push/vapid", response_model=VapidKey)
async def vapid_key() -> VapidKey:
    return VapidKey(public_key=await db.run(push_service.public_key))


@router.post("/sessions/{session_id}/push")
async def subscribe(session_id: str, body: PushSubscription, request: Request) -> dict:
    participant = await _current_participant(session_id, request)
    await db.run(
        push_service.save_subscription,
        session_id,
        participant["id"],
        {"endpoint": body.endpoint, "keys": body.keys},
    )
    return {"subscribed": True}
