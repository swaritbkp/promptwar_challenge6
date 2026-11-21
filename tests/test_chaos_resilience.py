"""Chaos / fault injection: upstream outages degrade to correct answers, never HTTP 500s."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hawakhata.app import create_app
from hawakhata.config import Settings
from hawakhata.core.metrics import CHAT_OUTCOMES, RATE_LIMIT_REJECTIONS, UPSTREAM_ERRORS
from hawakhata.integrations.gemini import GeminiCascadeClient
from tests.fakes import FakeRedis


def _asgi(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://chaos")


async def test_dual_aq_outage_open_meteo_timeout_and_google_500(
    sample_profile_data: dict[str, Any],
) -> None:
    hits: dict[str, int] = {"open_meteo": 0, "google_aq": 0}

    def upstream(request: httpx.Request) -> httpx.Response:
        if "open-meteo" in request.url.host:
            hits["open_meteo"] += 1
            raise httpx.ReadTimeout("injected timeout", request=request)
        hits["google_aq"] += 1
        return httpx.Response(500, json={"error": {"code": 500}})

    cfg = Settings(_env_file=None, app_env="dev", google_maps_api_key=SecretStr("fake-maps"))
    app = create_app(cfg)
    app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    before = {p: UPSTREAM_ERRORS.value(provider=p) for p in hits}
    async with _asgi(app) as client:
        brief = await client.post("/api/v1/brief", json={"profile": sample_profile_data})
        chat = await client.post("/api/v1/chat", json={"message": "Is it safe to walk now?"})
    assert brief.status_code == 200 and chat.status_code == 200
    assert brief.json()["meta"]["data_mode"] == "fixture"  # offline fixture, still numbers
    assert brief.json()["data"]["headline"] and chat.json()["data"]["grounded"]
    assert hits == {"open_meteo": 2, "google_aq": 2}  # 2 attempts each, then cached fallback
    for provider, n in hits.items():
        assert UPSTREAM_ERRORS.value(provider=provider) == before[provider] + n


@pytest.mark.parametrize(
    ("fallback_reply", "outcome"),
    [("", "fallback_empty"), ("PM2.5 will be 987654 today.", "fallback_ungrounded")],
)
def test_gemini_cascade_primary_429_then_bad_fallback_reply(
    fallback_reply: str, outcome: str
) -> None:
    cfg = Settings(
        _env_file=None,
        app_env="test",
        gemini_api_key=SecretStr("k"),
        gemini_model_primary="primary",
        gemini_model_fallback="fallback",
        ai_limit_per_min=100,
    )
    sdk = MagicMock()
    sdk.aio.models.generate_content = AsyncMock(
        side_effect=[Exception("429 RESOURCE_EXHAUSTED"), MagicMock(text=fallback_reply)]
    )
    app = create_app(cfg)
    app.state.gemini_client = GeminiCascadeClient(cfg, genai_client=sdk)
    before_outcome, before_err = (
        CHAT_OUTCOMES.value(outcome=outcome),
        UPSTREAM_ERRORS.value(provider="gemini"),
    )
    with TestClient(app) as client:
        res = client.post("/api/v1/chat", json={"message": "What now?"})
    data = res.json()["data"]
    assert res.status_code == 200 and data["degraded"] and data["grounded"]
    assert data["reply"].strip() and "987654" not in data["reply"]
    models = [c.kwargs["model"] for c in sdk.aio.models.generate_content.call_args_list]
    assert models == ["primary", "fallback"]
    assert CHAT_OUTCOMES.value(outcome=outcome) == before_outcome + 1
    assert UPSTREAM_ERRORS.value(provider="gemini") == before_err + 1


def test_mid_session_redis_outage_degrades_and_readyz_flips(
    sample_profile_data: dict[str, Any],
) -> None:
    redis = FakeRedis()
    app = create_app(Settings(_env_file=None, app_env="test"), redis_client=redis)  # type: ignore[arg-type]
    turn = {"message": "Is it safe to walk now?", "session_id": "chaosredis1"}
    with TestClient(app) as client:
        assert client.post("/api/v1/chat", json=turn).status_code == 200
        assert redis.calls > 0
        assert client.get("/readyz").json()["checks"]["redis"] == "ok"
        redis.down = True
        before = UPSTREAM_ERRORS.value(provider="redis")
        chat = client.post("/api/v1/chat", json=turn)
        brief = client.post("/api/v1/brief", json={"profile": sample_profile_data})
        ready = client.get("/readyz")
        degraded_errors = UPSTREAM_ERRORS.value(provider="redis") - before
        redis.down = False
        recovered = client.get("/readyz")
        hist = client.portal.call(app.state.sessions.history, "chaosredis1")  # type: ignore[union-attr]
    assert chat.status_code == 200 and chat.json()["data"]["grounded"]
    assert brief.status_code == 200 and brief.json()["data"]["headline"]
    assert ready.status_code == 503 and ready.json()["checks"]["redis"] == "fail"
    assert recovered.status_code == 200
    # rate limit (chat + brief) + session write + brief AQ cache get/set; never a 500
    assert degraded_errors >= 5
    assert len(hist) == 2  # turn 2 went to the in-memory fallback, Redis kept turn 1


@pytest.mark.parametrize("backend", ["memory", "redis"])
async def test_concurrent_burst_from_one_ip_gets_clean_429s(backend: str) -> None:
    cfg = Settings(_env_file=None, app_env="test", rate_limit_per_min=5)
    app = create_app(cfg, redis_client=FakeRedis() if backend == "redis" else None)  # type: ignore[arg-type]
    before = RATE_LIMIT_REJECTIONS.value()
    body = {"message": "Is it safe to walk now?"}
    headers = {"X-Forwarded-For": "203.0.113.77"}
    async with _asgi(app) as client:
        results = await asyncio.gather(
            *(client.post("/api/v1/chat", json=body, headers=headers) for _ in range(15))
        )
    codes = sorted(r.status_code for r in results)
    assert codes == [200] * 5 + [429] * 10
    limited = [r for r in results if r.status_code == 429]
    assert all(int(r.headers["retry-after"]) >= 1 for r in limited)
    assert all(r.json()["error"]["code"] == "RATE_LIMITED" for r in limited)
    assert RATE_LIMIT_REJECTIONS.value() == before + 10
