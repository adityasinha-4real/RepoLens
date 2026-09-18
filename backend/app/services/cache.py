"""Tiny in-process TTL + LRU cache. RepoLens is stateless; this only avoids repeating identical
work (and GitHub/AI calls) for requests that arrive within a few minutes of each other."""

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(
        self, max_entries: int, ttl_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_seconds
        self._clock = clock

    def get(self, key: str) -> T | None:
        item = self._data.get(key)
        if item is None:
            return None
        stored_at, value = item
        if self._clock() - stored_at > self._ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        if self._max <= 0 or self._ttl <= 0:
            return
        self._data[key] = (self._clock(), value)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)
