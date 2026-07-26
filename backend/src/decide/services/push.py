"""Web Push for async match alerts.

VAPID keys are generated once and stored in the config table. Sends are
best-effort: a dead subscription (404/410 from the push service) is deleted,
and no push failure ever breaks a swipe request.
"""

from __future__ import annotations

import json
import logging
import time

from .. import config, db

log = logging.getLogger(__name__)

_CLAIMS_SUB = "mailto:decide@localhost"


def ensure_vapid() -> str:
    """Create-or-load the VAPID keypair. Returns the public application
    server key (urlsafe base64). Blocking; call via db.run at startup."""
    public = config.get_value("vapid_public")
    private = config.get_value("vapid_private_pem")
    if public and private:
        return public

    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid, b64urlencode

    vapid = Vapid()
    vapid.generate_keys()
    private_pem = vapid.private_pem().decode()
    raw_public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public = b64urlencode(raw_public)
    config.set_value("vapid_private_pem", private_pem)
    config.set_value("vapid_public", public)
    return public


def public_key() -> str:
    return config.get_value("vapid_public") or ""


def save_subscription(session_id: str, participant_id: str, subscription: dict) -> None:
    conn = db.connect()
    conn.execute(
        "INSERT INTO push_subs (endpoint, participant_id, session_id, sub_json, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(endpoint) DO UPDATE SET participant_id = excluded.participant_id, "
        "session_id = excluded.session_id, sub_json = excluded.sub_json",
        (
            subscription["endpoint"],
            participant_id,
            session_id,
            json.dumps(subscription),
            int(time.time()),
        ),
    )
    conn.commit()


def send_for_session(
    session_id: str, payload: dict, exclude_participant: str | None = None
) -> int:
    """Push `payload` to every subscriber of a session. Blocking. Returns
    the number of successful sends."""
    conn = db.connect()
    rows = conn.execute(
        "SELECT endpoint, participant_id, sub_json FROM push_subs WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    if not rows:
        return 0

    private_pem = config.get_value("vapid_private_pem")
    if not private_pem:
        return 0

    from pywebpush import WebPushException, webpush

    sent = 0
    body = json.dumps(payload)
    for row in rows:
        if exclude_participant and row["participant_id"] == exclude_participant:
            continue
        try:
            webpush(
                subscription_info=json.loads(row["sub_json"]),
                data=body,
                vapid_private_key=private_pem,
                vapid_claims={"sub": _CLAIMS_SUB},
                ttl=6 * 3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):  # subscription expired — clean up
                conn.execute(
                    "DELETE FROM push_subs WHERE endpoint = ?", (row["endpoint"],)
                )
                conn.commit()
            else:
                log.info("push send failed (%s)", status)
        except Exception:
            log.exception("push send crashed")
    return sent
