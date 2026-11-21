"""Bounded abuse limits: a per-minute token bucket and a per-day usage quota."""

from __future__ import annotations

import hashlib
import ipaddress
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


def _valid_ip(raw: str) -> str | None:
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


def resolve_client_ip(forwarded_for: str | None, peer: str | None, trusted_hops: int) -> str:
    """Return the client IP recorded by the outermost trusted proxy.

    Each trusted proxy appends the address it saw to ``X-Forwarded-For``, so the
    ``trusted_hops``-th entry from the RIGHT is the real client; everything to its left is
    client-supplied and spoofable. Falls back to the socket peer when the header is absent,
    too short, invalid or ``trusted_hops == 0``.
    """
    if forwarded_for and trusted_hops > 0:
        hops = forwarded_for.split(",")
        if len(hops) >= trusted_hops:
            candidate = _valid_ip(hops[-trusted_hops])
            if candidate:
                return candidate
    return _valid_ip(peer or "") or "unknown"


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Allow per_minute requests per client with smooth refill."""

    def __init__(
        self, per_minute: int, max_clients: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
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
        """Consume one token for client; return False when rate limited."""
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
        """Return whole seconds until client regains one token."""
        bucket = self._buckets.get(client)
        if bucket is None or bucket.tokens >= 1.0:
            return 0
        return max(1, int((1.0 - bucket.tokens) / self._refill_per_s + 0.999))

    @property
    def tracked_clients(self) -> int:
        """Number of clients currently tracked."""
        return len(self._buckets)


class DailyQuota:
    """Cap expensive operations per client per rolling UTC day."""

    def __init__(
        self, max_per_day: int, max_clients: int, clock: Callable[[], float] = time.time
    ) -> None:
        if max_per_day <= 0 or max_clients <= 0:
            raise ValueError("max_per_day and max_clients must be positive")
        self._max_per_day = max_per_day
        self._max_clients = max_clients
        self._clock = clock
        self._usage: OrderedDict[str, tuple[int, int]] = OrderedDict()

    def _today(self) -> int:
        return int(self._clock() // 86_400)

    def try_consume(self, client: str) -> bool:
        """Record one use for client; return False once quota is spent."""
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
        """Return how many uses client has left today."""
        used_day, used = self._usage.get(client, (self._today(), 0))
        return self._max_per_day if used_day != self._today() else self._max_per_day - used
