"""Artwork proxy (constraint C2): the browser never talks to the PMS.

GET /api/art/{rating_key}?kind=poster|backdrop&w=&h=
Disk-cached with a strong ETag; upstream failure returns a generated SVG
placeholder, never a broken image.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from .. import db
from ..services.placeholder import build_svg

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/art", tags=["art"])

_DEFAULTS = {"poster": (600, 900), "backdrop": (1280, 720)}
CACHE_HEADERS = {"Cache-Control": "public, max-age=604800"}
PLACEHOLDER_HEADERS = {"Cache-Control": "public, max-age=300"}


def _placeholder(title: str, kind: str) -> Response:
    return Response(
        content=build_svg(title, kind),
        media_type="image/svg+xml",
        headers=PLACEHOLDER_HEADERS,
    )


@router.get("/{rating_key}")
async def get_art(
    rating_key: str,
    request: Request,
    kind: Literal["poster", "backdrop"] = "poster",
    w: int | None = Query(default=None, ge=50, le=1920),
    h: int | None = Query(default=None, ge=50, le=1920),
):
    default_w, default_h = _DEFAULTS[kind]
    width, height = w or default_w, h or default_h

    def _lookup_item():
        return db.connect().execute(
            "SELECT title, thumb, art FROM items WHERE id = ?", (rating_key,)
        ).fetchone()

    item = await db.run(_lookup_item)
    if item is None:
        raise HTTPException(status_code=404, detail="No such film in the library.")

    image_path = item["thumb"] if kind == "poster" else item["art"]
    if not image_path:
        return _placeholder(item["title"], kind)

    cache = request.app.state.artcache
    key = f"{rating_key}_{kind}_{width}x{height}"

    def _fetch() -> bytes:
        source = request.app.state.source_factory()
        data, _content_type = source.fetch_artwork(image_path, width, height)
        return data

    try:
        path, etag = await cache.get_or_fetch(key, _fetch)
    except Exception as exc:
        log.warning("artwork fetch failed for %s: %s", key, type(exc).__name__)
        return _placeholder(item["title"], kind)

    quoted = f'"{etag}"'
    if request.headers.get("if-none-match") == quoted:
        return Response(status_code=304, headers={**CACHE_HEADERS, "ETag": quoted})
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={**CACHE_HEADERS, "ETag": quoted},
    )
