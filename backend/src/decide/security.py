"""Secrets: signing key bootstrap, participant cookie HMAC, log redaction.

C1: the Plex token must never appear in a response body or a log line. The
redaction filter is belt-and-braces on top of simply never logging it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets as _secrets

from . import config

COOKIE_NAME = "decide_pid"
_REDACT = "***redacted***"

# Every secret value this process has seen (plex tokens, signing key). The
# redaction filter masks these in any log record that slips through.
_known_secrets: set[str] = set()

_signing_key: bytes | None = None


def add_secret(value: str | None) -> None:
    if value and len(value) >= 8:
        _known_secrets.add(value)


def bootstrap() -> None:
    """Load or create the signing key. Runs in a DB thread at startup."""
    global _signing_key
    env = config._settings().env_secret_key
    if env:
        _signing_key = hashlib.sha256(env.encode()).digest()
        add_secret(env)
        return
    stored = config.get_value("secret_key")
    if stored is None:
        stored = _secrets.token_bytes(32).hex()
        config.set_value("secret_key", stored)
    _signing_key = bytes.fromhex(stored)
    add_secret(stored)


def _key() -> bytes:
    if _signing_key is None:
        raise RuntimeError("security.bootstrap() has not been called")
    return _signing_key


def sign_participant(participant_id: str) -> str:
    payload = f"v1.{participant_id}"
    sig = hmac.new(_key(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def verify_participant(cookie_value: str | None) -> str | None:
    """Return the participant id if the cookie is validly signed, else None."""
    if not cookie_value:
        return None
    parts = cookie_value.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return None
    expected = sign_participant(parts[1])
    if hmac.compare_digest(expected, cookie_value):
        return parts[1]
    return None


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if _known_secrets:
            msg = record.getMessage()
            hit = False
            for s in _known_secrets:
                if s in msg:
                    msg = msg.replace(s, _REDACT)
                    hit = True
            if hit:
                record.msg = msg
                record.args = ()
        return True


def install_redaction() -> None:
    """Attach the redaction filter to every handler currently configured.

    Handler-level (not logger-level) because propagated records bypass
    ancestor loggers' own filters.
    """
    flt = RedactionFilter()
    seen: set[int] = set()
    loggers = [logging.getLogger()] + [
        logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    ]
    for logger in loggers:
        for handler in logger.handlers:
            if id(handler) not in seen:
                handler.addFilter(flt)
                seen.add(id(handler))
