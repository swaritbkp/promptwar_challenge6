"""Bounded caching behind one async protocol.

``TTLCache`` is the default in-process backend: LRU-evicted at ``max_entries``
and expired after ``ttl_s``. ``RedisCache`` is a drop-in backend for Redis /
Memorystore when ``REDIS_URL`` is configured, so horizontally scaled Cloud Run
instances can share cached Google Air Quality responses.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from hawakhata.config import Settings

JsonValue = dict[str, object] | list[object] | str | int | float | bool | None


@dataclass(slots=True)
class CacheStats:
    """Counters exposed for observability (hits, misses, evictions, current size)."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0


class CacheBackend(Protocol):
    """Async key-value cache contract shared by all backends."""

    async def get(self, key: str) -> JsonValue:
        """Return the cached value or ``None`` when missing or expired."""
        ...

    async def set(self, key: str, value: JsonValue, ttl_s: int | None = None) -> None:
        """Store a JSON-serialisable value with an optional per-key TTL."""
        ...

    def stats(self) -> CacheStats:
        """Return a snapshot of cache counters."""
        ...


class TTLCache:
    """In-memory LRU cache with a hard size bound and per-entry expiry.

    Complexity: O(1) average for ``get`` and ``set``. Memory is bounded by
    ``max_entries``; the least-recently-used entry is evicted first.
    """

    def __init__(
        self,
        max_entries: int,
        default_ttl_s: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a cache holding at most ``max_entries`` items.

        Raises:
            ValueError: If ``max_entries`` or ``default_ttl_s`` is not positive.
        """
        if max_entries <= 0 or default_ttl_s <= 0:
            raise ValueError("max_entries and default_ttl_s must be positive")
        self._max_entries = max_entries
        self._default_ttl_s = default_ttl_s
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, JsonValue]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stats = CacheStats()

    async def get(self, key: str) -> JsonValue:
        """Return a live value (refreshing its LRU position) or ``None``."""
        async with self._lock:
            entry = self._data.get(key)
            if entry is None or entry[0] <= self._clock():
                if entry is not None:
                    del self._data[key]
                self._stats.misses += 1
                return None
            self._data.move_to_end(key)
            self._stats.hits += 1
            return entry[1]

    async def set(self, key: str, value: JsonValue, ttl_s: int | None = None) -> None:
        """Insert or replace ``key``; evict LRU entries beyond ``max_entries``."""
        expires_at = self._clock() + (ttl_s or self._default_ttl_s)
        async with self._lock:
            self._data[key] = (expires_at, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)
                self._stats.evictions += 1

    def stats(self) -> CacheStats:
        """Return counters including the current number of stored entries."""
        return CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            evictions=self._stats.evictions,
            size=len(self._data),
        )


class RedisCache:
    """Redis-backed cache; values are JSON encoded and always carry a TTL."""

    def __init__(self, client: Redis, default_ttl_s: int, prefix: str = "hk:") -> None:
        """Wrap an async Redis client; keys are namespaced with ``prefix``."""
        self._client = client
        self._default_ttl_s = default_ttl_s
        self._prefix = prefix
        self._stats = CacheStats()

    async def get(self, key: str) -> JsonValue:
        """Return the decoded value or ``None``."""
        raw = await self._client.get(self._prefix + key)
        if raw is None:
            self._stats.misses += 1
            return None
        self._stats.hits += 1
        decoded: JsonValue = json.loads(raw)
        return decoded

    async def set(self, key: str, value: JsonValue, ttl_s: int | None = None) -> None:
        """Store ``value`` with an expiry (Redis evicts expired keys itself)."""
        await self._client.set(
            self._prefix + key, json.dumps(value), ex=ttl_s or self._default_ttl_s
        )

    def stats(self) -> CacheStats:
        """Return hit/miss counters (size is managed by Redis)."""
        return CacheStats(hits=self._stats.hits, misses=self._stats.misses)


def build_cache(settings: Settings) -> CacheBackend:
    """Choose the cache backend from configuration (Redis if ``REDIS_URL`` is set)."""
    if settings.redis_url:
        from redis.asyncio import Redis  # noqa: PLC0415 - optional dependency path

        return RedisCache(Redis.from_url(settings.redis_url), settings.aq_cache_ttl_s)
    return TTLCache(settings.cache_max_entries, settings.aq_cache_ttl_s)
