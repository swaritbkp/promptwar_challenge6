"""Hermetic in-process async Redis double (no daemon, no extra packages).

Covers the commands HawaKhata uses: GET / SET ex / SETEX / EXPIRE / PING / register_script.
``lupa`` is not installed, so fakeredis cannot run Lua; ``register_script`` instead returns a
line-for-line Python mirror of ``RATE_BUCKET_LUA`` run under one lock (atomic like Redis).
Set ``down = True`` to simulate an outage: every command raises ``redis.ConnectionError``.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence

from redis.exceptions import ConnectionError as RedisConnectionError

from hawakhata.core.rate_limit import RATE_BUCKET_LUA


class FakeRedis:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.down = False
        self.calls = 0
        self._lock = threading.Lock()  # TestClients run apps on separate threads/loops
        self._data: dict[str, tuple[object, float | None]] = {}

    def _guard(self) -> None:
        self.calls += 1
        if self.down:
            raise RedisConnectionError("fake redis is down")

    def _live(self, key: str) -> object | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry[1] is not None and entry[1] <= self.clock():
            del self._data[key]
            return None
        return entry[0]

    async def get(self, key: str) -> object | None:
        self._guard()
        with self._lock:
            return self._live(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._guard()
        with self._lock:
            self._data[key] = (value, self.clock() + ex if ex else None)
        return True

    async def setex(self, key: str, ttl_s: int, value: str) -> bool:
        return await self.set(key, value, ex=ttl_s)

    async def expire(self, key: str, ttl_s: int) -> bool:
        self._guard()
        with self._lock:
            value = self._live(key)
            if value is None:
                return False
            self._data[key] = (value, self.clock() + ttl_s)
            return True

    def ttl(self, key: str) -> float | None:
        entry = self._data.get(key)
        return None if entry is None or entry[1] is None else entry[1] - self.clock()

    async def ping(self) -> bool:
        self._guard()
        return True

    async def aclose(self) -> None:
        return None

    def register_script(self, script: str) -> Callable[..., object]:
        assert script == RATE_BUCKET_LUA, "only the rate-bucket script is mirrored"

        async def run(keys: Sequence[str], args: Sequence[float]) -> list[int]:
            self._guard()
            capacity, refill, ttl = float(args[0]), float(args[1]), int(args[2])
            with self._lock:
                now = self.clock()
                state = self._live(keys[0])
                tokens, ts = state if isinstance(state, tuple) else (capacity, now)
                tokens = min(capacity, tokens + max(0.0, now - ts) * refill)
                allowed, retry = 0, 0
                if tokens >= 1:
                    tokens, allowed = tokens - 1, 1
                else:
                    retry = math.ceil((1 - tokens) / refill)
                self._data[keys[0]] = ((tokens, now), now + ttl)
            return [allowed, retry]

        return run
