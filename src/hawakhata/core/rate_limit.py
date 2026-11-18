"""Bounded abuse limits: a per-minute token bucket and a per-day usage quota.

Both are keyed by a hashed client identifier and keep a size-bounded LRU table,
so memory cannot grow without limit under a flood of distinct clients.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Allow ``per_minute`` requests per client with smooth refill.

    The client table is an LRU bounded by ``max_clients`` so memory cannot grow
    without limit under a flood of distinct IPs.
    """

    def __init__(
        self,
        per_minute: int,
        max_clients: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a limiter.

        Raises:
            ValueError: If ``per_minute`` or ``max_clients`` is not positive.
        """
        if per_minute <= 0 or max_clients <= 0:
            raise ValueError("per_minute and max_clients must be positive")
        self._capacity = float(per_minute)
        self._refill_per_s = per_minute / 60.0
        self._max_clients = max_clients
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    @staticmethod
    def client_key(raw_identifier: str) -> str:
        """Hash an IP/identifier so raw addresses are never stored."""
        return hashlib.sha256(raw_identifier.encode("utf-8")).hexdigest()[:16]

    def allow(self, client: str) -> bool:
        """Consume one token for ``client``; return False when rate limited."""
        now = self._clock()
        bucket = self._buckets.get(client)
        if bucket is None:
            bucket = _Bucket(tokens=self._capacity, updated_at=now)
            self._buckets[client] = bucket
            if len(self._buckets) > self._max_clients:
                self._buckets.popitem(last=False)
        else:
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_per_s)
            bucket.updated_at = now
            self._buckets.move_to_end(client)
        if bucket.tokens < 1.0:
            return False
        bucket.tokens -= 1.0
        return True

    def retry_after_s(self, client: str) -> int:
        """Return whole seconds until ``client`` regains one token."""
        bucket = self._buckets.get(client)
        if bucket is None or bucket.tokens >= 1.0:
            return 0
        return max(1, int((1.0 - bucket.tokens) / self._refill_per_s + 0.999))

    @property
    def tracked_clients(self) -> int:
        """Number of clients currently tracked (never exceeds ``max_clients``)."""
        return len(self._buckets)


class DailyQuota:
    """Cap expensive operations (Gemini calls) per client per rolling UTC day.

    Each AI feature gets its own instance so one feature cannot exhaust another's
    budget. Day boundaries come from the injected clock (seconds since epoch).
    """

    def __init__(
        self,
        max_per_day: int,
        max_clients: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create a quota.

        Raises:
            ValueError: If ``max_per_day`` or ``max_clients`` is not positive.
        """
        if max_per_day <= 0 or max_clients <= 0:
            raise ValueError("max_per_day and max_clients must be positive")
        self._max_per_day = max_per_day
        self._max_clients = max_clients
        self._clock = clock
        self._usage: OrderedDict[str, tuple[int, int]] = OrderedDict()

    def _today(self) -> int:
        return int(self._clock() // 86_400)

    def try_consume(self, client: str) -> bool:
        """Record one use for ``client``; return False once today's quota is spent."""
        day = self._today()
        used_day, used = self._usage.get(client, (day, 0))
        if used_day != day:
            used = 0
        if used >= self._max_per_day:
            return False
        self._usage[client] = (day, used + 1)
        self._usage.move_to_end(client)
        while len(self._usage) > self._max_clients:
            self._usage.popitem(last=False)
        return True

    def remaining(self, client: str) -> int:
        """Return how many uses ``client`` has left today."""
        used_day, used = self._usage.get(client, (self._today(), 0))
        return self._max_per_day if used_day != self._today() else self._max_per_day - used
