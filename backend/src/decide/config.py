"""Settings and config-table access.

Precedence everywhere: environment variable, then the config table in SQLite.
Env vars (PLEX_URL, PLEX_TOKEN, PLEX_SECTIONS) exist for declarative setups
and skip the wizard when they fully describe a connection.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import db


@dataclass
class Settings:
    data_dir: Path
    port: int = 8080
    env_plex_url: str | None = None
    env_plex_token: str | None = None
    env_plex_sections: list[str] | None = None
    env_secret_key: str | None = None
    env_local_url: str | None = None
    env_remote_url: str | None = None
    enable_jobs: bool = True
    static_dir: Path | None = None
    incremental_interval_s: int = 6 * 3600
    purge_interval_s: int = 15 * 60
    art_cache_mb: int = 500
    extra: dict = field(default_factory=dict)


def load_settings() -> Settings:
    sections_raw = os.environ.get("PLEX_SECTIONS")
    static = os.environ.get("STATIC_DIR")
    return Settings(
        data_dir=Path(os.environ.get("DATA_DIR", "/data")),
        port=int(os.environ.get("PORT", "8080")),
        env_plex_url=os.environ.get("PLEX_URL") or None,
        env_plex_token=os.environ.get("PLEX_TOKEN") or None,
        env_plex_sections=[s.strip() for s in sections_raw.split(",") if s.strip()]
        if sections_raw
        else None,
        env_secret_key=os.environ.get("SECRET_KEY") or None,
        env_local_url=os.environ.get("LOCAL_URL") or None,
        env_remote_url=os.environ.get("REMOTE_URL") or None,
        static_dir=Path(static) if static else None,
        art_cache_mb=int(os.environ.get("ART_CACHE_MB", "500")),
    )


# The active Settings for this process; set once by the app factory.
SETTINGS: Settings | None = None


def init(settings: Settings) -> None:
    global SETTINGS
    SETTINGS = settings


def _settings() -> Settings:
    if SETTINGS is None:
        raise RuntimeError("config.init() has not been called")
    return SETTINGS


# ---- config table (call these via db.run from async code) ----

def get_value(key: str) -> str | None:
    row = db.connect().execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_value(key: str, value: str) -> None:
    conn = db.connect()
    conn.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def delete_value(key: str) -> None:
    conn = db.connect()
    conn.execute("DELETE FROM config WHERE key = ?", (key,))
    conn.commit()


# ---- Plex connection facts (env first, then config table) ----

def get_plex_token() -> str | None:
    return _settings().env_plex_token or get_value("plex_token")


def get_plex_url() -> str | None:
    return _settings().env_plex_url or get_value("plex_url")


def get_server_token() -> str | None:
    """Token to use against the PMS itself. Shared servers get their own
    access token from discovery; owned servers use the account token."""
    return (
        _settings().env_plex_token
        or get_value("plex_access_token")
        or get_value("plex_token")
    )


def get_sections() -> list[str] | None:
    env = _settings().env_plex_sections
    if env:
        return env
    raw = get_value("plex_sections")
    return json.loads(raw) if raw else None


def get_server_identity() -> tuple[str | None, str | None]:
    """(machine_identifier, friendly_name) of the chosen server, if known."""
    return get_value("server_machine_id"), get_value("server_name")


def setup_stage() -> str:
    """unconfigured -> needs_server -> needs_sections -> ready"""
    if not get_plex_token():
        return "unconfigured"
    if not get_plex_url():
        return "needs_server"
    if not get_sections():
        return "needs_sections"
    return "ready"
