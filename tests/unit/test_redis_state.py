"""Sprint 2: Redis-shared sessions + rate limits, failover, bounded prompt memory."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from hawakhata.agent.sessions import (
    FailoverSessionStore,
    RedisSessionStore,
    SessionStore,
    bounded_history,
    build_session_store,
)
from hawakhata.app import create_app
from hawakhata.config import Settings
from hawakhata.core.cache import RedisCache, TTLCache, build_cache
from hawakhata.core.metrics import UPSTREAM_ERRORS
from hawakhata.core.rate_limit import (
    FailoverRateLimiter,
    RedisTokenBucketLimiter,
    TokenBucketLimiter,
    build_rate_limiter,
)
from tests.conftest import FakeClock
from tests.fakes import FakeRedis

IP = {"X-Forwarded-For": "203.0.113.50"}


def _cfg(**kw: Any) -> Settings:
    return Settings(_env_file=None, app_env="test", **kw)


async def test_two_redis_session_stores_share_history_with_ttl_and_bound(
    clock: FakeClock,
) -> None:
    redis = FakeRedis(clock)
    a = RedisSessionStore(redis, ttl_s=60, max_turns=3)  # type: ignore[arg-type]
    b = RedisSessionStore(redis, ttl_s=60, max_turns=3)  # type: ignore[arg-type]
    await a.append_turns("s1", [("user", "hi"), ("model", "hello")])
    await b.append_turns("s1", [("user", "again"), ("model", "sure")])
    assert [t["content"] for t in await a.history("s1")] == ["hello", "again", "sure"]
    assert await b.history("other") == []
    key = a._key("s1")
    assert "s1" not in key and redis.ttl(key) == 60
    clock.advance(59)
    await b.history("s1")  # sliding TTL refresh
    assert redis.ttl(key) == 60
    clock.advance(61)
    assert await a.history("s1") == []
    with pytest.raises(ValueError, match="positive"):
        RedisSessionStore(redis, ttl_s=0, max_turns=1)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", ["not json", '{"a": 1}', '[1, {"role": 2, "content": "x"}]'])
async def test_corrupt_session_payload_reads_as_empty(raw: str) -> None:
    redis = FakeRedis()
    store = RedisSessionStore(redis, ttl_s=60, max_turns=5)  # type: ignore[arg-type]
    await redis.set(store._key("s"), raw)
    assert await store.history("s") == []


async def test_session_failover_degrades_to_memory_and_counts_redis_errors() -> None:
    redis = FakeRedis()
    store = FailoverSessionStore(
        RedisSessionStore(redis, ttl_s=60, max_turns=4),  # type: ignore[arg-type]
        SessionStore(),
    )
    await store.append_turns("s", [("user", "a")])
    redis.down = True
    before = UPSTREAM_ERRORS.value(provider="redis")
    await store.append_turns("s", [("user", "b")])
    assert [t["content"] for t in await store.history("s")] == ["b"]
    assert UPSTREAM_ERRORS.value(provider="redis") == before + 2
    redis.down = False
    assert [t["content"] for t in await store.history("s")] == ["a"]


def test_builders_pick_backend_from_redis_client() -> None:
    cfg, redis = _cfg(), FakeRedis()
    assert isinstance(build_session_store(cfg, None), SessionStore)
    assert isinstance(build_session_store(cfg, redis), FailoverSessionStore)  # type: ignore[arg-type]
    assert isinstance(build_rate_limiter(cfg, None), TokenBucketLimiter)
    assert isinstance(build_rate_limiter(cfg, redis), FailoverRateLimiter)  # type: ignore[arg-type]
    assert isinstance(build_cache(cfg, redis), RedisCache)  # type: ignore[arg-type]
    assert isinstance(build_cache(cfg), TTLCache)


async def test_redis_bucket_is_shared_refills_and_expires(clock: FakeClock) -> None:
    redis = FakeRedis(clock)
    a = RedisTokenBucketLimiter(redis, per_minute=2)  # type: ignore[arg-type]
    b = RedisTokenBucketLimiter(redis, per_minute=2)  # type: ignore[arg-type]
    assert [await a.acquire("c"), await b.acquire("c")] == [(True, 0), (True, 0)]
    assert await a.acquire("c") == (False, 30)  # 1 token / 30 s
    assert await b.acquire("other") == (True, 0)
    clock.advance(30)
    assert await b.acquire("c") == (True, 0)
    assert redis.ttl("hk:rl:c") == 61
    with pytest.raises(ValueError, match="positive"):
        RedisTokenBucketLimiter(redis, per_minute=0)  # type: ignore[arg-type]


async def test_rate_limit_failover_uses_local_bucket_during_outage() -> None:
    redis = FakeRedis()
    limiter = FailoverRateLimiter(
        RedisTokenBucketLimiter(redis, per_minute=1),  # type: ignore[arg-type]
        TokenBucketLimiter(per_minute=1, max_clients=10),
    )
    assert await limiter.acquire("c") == (True, 0)
    redis.down = True
    before = UPSTREAM_ERRORS.value(provider="redis")
    assert (await limiter.acquire("c"))[0] is True  # fresh local bucket, never a 500
    allowed, retry = await limiter.acquire("c")
    assert not allowed and retry >= 1
    assert UPSTREAM_ERRORS.value(provider="redis") == before + 2


async def test_redis_cache_outage_is_a_miss_not_an_error() -> None:
    redis = FakeRedis()
    cache = RedisCache(redis, default_ttl_s=60)  # type: ignore[arg-type]
    await cache.set("k", {"v": 1})
    redis.down = True
    await cache.set("k", {"v": 2})
    assert await cache.get("k") is None
    redis.down = False
    assert await cache.get("k") == {"v": 1}


def test_two_app_instances_share_chat_history_and_one_rate_bucket() -> None:
    redis = FakeRedis()
    cfg = _cfg(rate_limit_per_min=3)
    app_a = create_app(cfg, redis_client=redis)  # type: ignore[arg-type]
    app_b = create_app(cfg, redis_client=redis)  # type: ignore[arg-type]
    with TestClient(app_a) as a, TestClient(app_b) as b:
        body = {"message": "Is it safe to walk now?", "session_id": "shared01"}
        assert a.post("/api/v1/chat", json=body, headers=IP).status_code == 200
        assert b.post("/api/v1/chat", json=body, headers=IP).status_code == 200
        hist_a = a.portal.call(app_a.state.sessions.history, "shared01")  # type: ignore[union-attr]
        hist_b = b.portal.call(app_b.state.sessions.history, "shared01")  # type: ignore[union-attr]
        statuses = [
            a.get("/api/v1/meta", headers=IP).status_code,
            b.get("/api/v1/meta", headers=IP).status_code,
        ]
        meta = a.get("/api/v1/meta", headers={"X-Forwarded-For": "198.51.100.9"})
    assert len(hist_a) == 4 and hist_a == hist_b
    assert statuses == [200, 429]  # 3 tokens shared: chat A, chat B, meta A; then B is limited
    assert meta.json()["data"]["runtime"]["state_backend"] == "redis"


@pytest.mark.parametrize(
    ("turns", "chars", "expected"),
    [
        (8, 6000, ["m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9"]),  # newest 8 of 10
        (3, 6000, ["m7", "m8", "m9"]),
        (8, 2 * 13, ["m8", "m9"]),  # each "user: m? pad" line + newline costs 13 chars
        (8, 12, []),
        (0, 6000, []),
    ],
)
def test_bounded_history_prunes_oldest_by_turns_then_chars(
    turns: int, chars: int, expected: list[str]
) -> None:
    entries = [{"role": "user", "content": f"m{i} pad"} for i in range(10)]
    kept = bounded_history(entries, turns, chars)
    assert [e["content"].split()[0] for e in kept] == expected
    assert sum(len(e["role"]) + len(e["content"]) + 3 for e in kept) <= chars


async def test_agent_prompt_history_is_bounded_by_settings() -> None:
    from unittest.mock import AsyncMock, MagicMock  # noqa: PLC0415

    import httpx  # noqa: PLC0415
    from pydantic import SecretStr  # noqa: PLC0415

    from hawakhata.agent.agent import HawaKhataAgent  # noqa: PLC0415
    from hawakhata.api.schemas import (  # noqa: PLC0415
        FamilyProfileInput,
        LocationInput,
        MemberInput,
    )
    from hawakhata.integrations.air_quality import AirQualityClient  # noqa: PLC0415
    from hawakhata.integrations.gemini import GeminiCascadeClient  # noqa: PLC0415

    cfg = _cfg(gemini_api_key=SecretStr("k"), gemini_model_primary="m1", ai_limit_per_min=100)
    sdk = MagicMock()
    sdk.aio.models.generate_content = AsyncMock(return_value=MagicMock(text="General guidance."))
    store = SessionStore()
    for i in range(10):
        store.add_message("s", "user", f"old-turn-{i} " + "x" * 50)
    agent = HawaKhataAgent(
        GeminiCascadeClient(cfg, genai_client=sdk), store, history_turns=4, history_max_chars=150
    )
    loc = LocationInput(lat=28.4595, lng=77.0266, city_name="Demo Area")
    profile = FamilyProfileInput(
        id="f", name="F", location=loc, members=[MemberInput(id="m", name="A", age_band="adult")]
    )
    aq = AirQualityClient(settings=cfg, cache=TTLCache(64, 3600), http_client=httpx.AsyncClient())
    await agent.run_turn("s", "What now?", profile=profile, location=loc, aq_client=aq)
    prompt = sdk.aio.models.generate_content.call_args.kwargs["contents"]
    history = prompt.split("<conversation_history>\n")[1].split("\n</conversation_history>")[0]
    assert "old-turn-9" in history and "old-turn-8" in history and "old-turn-7" not in history
    assert len(history) <= 150
