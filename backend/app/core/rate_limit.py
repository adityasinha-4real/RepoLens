"""In-memory sliding-window rate limiting and client identification.

Per-process state is enough for a single instance (the free-tier deployment model). With
several replicas, put a shared limiter (e.g. at the proxy/CDN) in front instead.
"""

import hmac
import ipaddress
import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.core.config import Settings

MAX_TRACKED_CLIENTS = 10_000
PROXY_SECRET_HEADER = "x-repolens-proxy-secret"  # noqa: S105 - a header name, not a secret
PROXY_CLIENT_IP_HEADER = "x-repolens-client-ip"


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


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_id(request: Request, settings: Settings) -> str:
    """The caller's IP for rate limiting. Headers are trusted only when it is safe to:

    1. PROXY_SHARED_SECRET set and the request carries it: use X-RepoLens-Client-IP, which the
       RepoLens frontend proxy fills in (works even when the API itself is publicly reachable).
    2. TRUST_PROXY_HEADERS: use the first X-Forwarded-For entry. Only for deployments where
       the API is reachable exclusively through a trusted proxy (e.g. a private network).
    3. Otherwise the TCP peer address.
    """
    secret = settings.proxy_shared_secret
    if secret is not None:
        supplied = request.headers.get(PROXY_SECRET_HEADER, "")
        if supplied and hmac.compare_digest(supplied.encode(), secret.get_secret_value().encode()):
            ip = _valid_ip(request.headers.get(PROXY_CLIENT_IP_HEADER, ""))
            if ip:
                return ip
    if settings.trust_proxy_headers:
        ip = _valid_ip(request.headers.get("x-forwarded-for", "").split(",")[0])
        if ip:
            return ip
    return request.client.host if request.client else "unknown"
