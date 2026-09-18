"""In-memory sliding-window rate limiting and client identification.

Per-process state is enough for a single instance (the free-tier deployment model). With
several replicas, put a shared limiter (e.g. at the proxy/CDN) in front instead.
"""

import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

MAX_TRACKED_CLIENTS = 10_000


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> int | None:
        """Record a hit for `key`. Returns None when allowed, else seconds until retry."""
        if self.limit <= 0:
            return None
        now = self._clock()
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= MAX_TRACKED_CLIENTS:
                self._evict(now)
            hits = self._hits[key] = deque()
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(1, math.ceil(self.window - (now - hits[0])))
        hits.append(now)
        return None

    def _evict(self, now: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window]:
            del self._hits[key]
        while len(self._hits) >= MAX_TRACKED_CLIENTS:  # still full: drop the oldest entry
            self._hits.pop(next(iter(self._hits)))


def client_id(request: Request, trust_proxy_headers: bool) -> str:
    """The caller's IP. X-Forwarded-For is only honored behind a trusted proxy, because
    clients can set it to anything."""
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    return request.client.host if request.client else "unknown"
