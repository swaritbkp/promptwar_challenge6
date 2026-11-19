from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import (
    AirQualityClient,
    CircuitBreaker,
    CircuitState,
    HourlyAirSeries,
    round_coordinates,
)


def test_round_coordinates() -> None:
    lat, lng = round_coordinates(28.45923, 77.02664)
    assert lat == 28.46 and lng == 77.03


def test_circuit_breaker_transitions() -> None:
    now = 1000.0
    cb = CircuitBreaker(failure_threshold=3, recovery_time_s=60.0, clock=lambda: now)
    assert cb.state == CircuitState.CLOSED and cb.can_execute() is True
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN and cb.can_execute() is False
    now += 30.0
    assert cb.can_execute() is False
    now += 31.0
    assert cb.can_execute() is True and cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


async def _client_call(
    settings: Settings | None = None,
    cache: TTLCache | None = None,
    transport: httpx.BaseTransport | None = None,
) -> AirQualityClient:
    s = settings or Settings(google_maps_api_key=None, app_env="test")
    c = cache or TTLCache(max_entries=100, default_ttl_s=3600)
    return AirQualityClient(settings=s, cache=c, http_client=httpx.AsyncClient(transport=transport))


@pytest.mark.asyncio
async def test_get_hourly_forecast_fixture_fallback_no_key() -> None:
    client = await _client_call()
    res = await client.get_hourly_forecast(lat=28.45, lng=77.02, hours=24)
    assert isinstance(res, HourlyAirSeries) and res.data_mode == "fixture" and len(res.points) == 24


@pytest.mark.asyncio
async def test_get_hourly_forecast_nearest_fixture_chandigarh() -> None:
    client = await _client_call()
    res = await client.get_hourly_forecast(lat=30.73, lng=76.78, hours=24)
    assert res.data_mode == "fixture" and len(res.points) == 24


@pytest.mark.asyncio
async def test_get_hourly_forecast_caching() -> None:
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    client = await _client_call(cache=cache)
    res1 = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=24)
    res2 = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=24)
    assert res1.location_cell == res2.location_cell and cache.stats().hits >= 1


@pytest.mark.asyncio
async def test_get_current_conditions() -> None:
    client = await _client_call()
    point = await client.get_current_conditions(lat=28.46, lng=77.03)
    assert point.pm25_ug_m3 > 0 and point.category_local != ""


@pytest.mark.asyncio
async def test_air_quality_timeout_and_breaker_failure() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    s = Settings(google_maps_api_key=SecretStr("test_key"), app_env="test")
    client = await _client_call(settings=s, transport=httpx.MockTransport(timeout_handler))
    res = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=12)
    assert res.data_mode == "fixture" and len(res.points) == 12


@pytest.mark.asyncio
async def test_demo_clock_iso_parsing() -> None:
    c1 = await _client_call(
        settings=Settings(google_maps_api_key=None, demo_clock_iso="2026-11-18T10:00:00Z")
    )
    res1 = await c1.get_hourly_forecast(lat=28.46, lng=77.03, hours=5)
    assert res1.points[0].time_local == "10:00"
    c2 = await _client_call(
        settings=Settings(google_maps_api_key=None, demo_clock_iso="invalid-date")
    )
    res2 = await c2.get_hourly_forecast(lat=28.46, lng=77.03, hours=5)
    assert len(res2.points) == 5
