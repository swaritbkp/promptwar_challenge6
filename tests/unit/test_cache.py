from __future__ import annotations

import asyncio

import fakeredis
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.config import Settings
from hawakhata.core.cache import RedisCache, TTLCache, build_cache
from tests.conftest import FakeClock


async def test_get_returns_stored_value_until_expiry(clock: FakeClock) -> None:
    cache = TTLCache(max_entries=4, default_ttl_s=60, clock=clock)
    await cache.set("k", {"pm25": 180})
    assert await cache.get("k") == {"pm25": 180}
    clock.advance(61)
    assert await cache.get("k") is None
    assert cache.stats().size == 0


async def test_per_key_ttl_overrides_default(clock: FakeClock) -> None:
    cache = TTLCache(max_entries=4, default_ttl_s=60, clock=clock)
    await cache.set("short", 1, ttl_s=5)
    clock.advance(6)
    assert await cache.get("short") is None


async def test_least_recently_used_entry_is_evicted_first(clock: FakeClock) -> None:
    cache = TTLCache(max_entries=2, default_ttl_s=60, clock=clock)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.get("a")  # "b" is now least recently used
    await cache.set("c", 3)
    assert await cache.get("b") is None
    assert await cache.get("a") == 1
    assert cache.stats().evictions == 1


async def test_stats_count_hits_and_misses(clock: FakeClock) -> None:
    cache = TTLCache(max_entries=2, default_ttl_s=60, clock=clock)
    await cache.set("a", 1)
    await cache.get("a")
    await cache.get("missing")
    stats = cache.stats()
    assert (stats.hits, stats.misses) == (1, 1)


@pytest.mark.parametrize(("max_entries", "ttl"), [(0, 10), (10, 0)])
def test_invalid_bounds_are_rejected(max_entries: int, ttl: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        TTLCache(max_entries=max_entries, default_ttl_s=ttl)


@settings(max_examples=100, deadline=None)
@given(keys=st.lists(st.text(min_size=1, max_size=8), max_size=200), bound=st.integers(1, 20))
def test_cache_never_exceeds_max_entries(keys: list[str], bound: int) -> None:
    async def run() -> int:
        cache = TTLCache(max_entries=bound, default_ttl_s=60)
        for key in keys:
            await cache.set(key, key)
        return cache.stats().size

    assert asyncio.run(run()) <= bound


async def test_redis_cache_round_trip_and_stats() -> None:
    cache = RedisCache(fakeredis.FakeAsyncRedis(), default_ttl_s=60)
    assert await cache.get("x") is None
    await cache.set("x", {"aqi": 412})
    assert await cache.get("x") == {"aqi": 412}
    assert (cache.stats().hits, cache.stats().misses) == (1, 1)


def test_build_cache_selects_backend_from_config() -> None:
    assert isinstance(build_cache(Settings(_env_file=None)), TTLCache)
    redis_settings = Settings(_env_file=None, redis_url="redis://localhost:6379/0")
    assert isinstance(build_cache(redis_settings), RedisCache)
