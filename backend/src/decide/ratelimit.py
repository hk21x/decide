"""In-memory sliding-window rate limiter (single process, no Redis)."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window_s
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


# Join-code lookups: 10 per minute per IP (brief §4.4).
code_lookup_limiter = RateLimiter(limit=10, window_s=60)
