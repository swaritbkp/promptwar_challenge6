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
    # 28.45923, 77.02664 -> 28.46, 77.03
    lat, lng = round_coordinates(28.45923, 77.02664)
    assert lat == 28.46
    assert lng == 77.03


def test_circuit_breaker_transitions() -> None:
    now = 1000.0

    def fake_clock() -> float:
        return now

    cb = CircuitBreaker(failure_threshold=3, recovery_time_s=60.0, clock=fake_clock)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 1st and 2nd failures
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # 3rd failure opens breaker
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Advance clock by 30s (< 60s) -> still OPEN
    now += 30.0
    assert cb.can_execute() is False

    # Advance clock past 60s -> HALF_OPEN
    now += 31.0
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Success resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_get_hourly_forecast_fixture_fallback_no_key() -> None:
    settings = Settings(google_maps_api_key=None, app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient() as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)

        # Query near Delhi/Gurugram (28.45, 77.02)
        res = await client.get_hourly_forecast(lat=28.45, lng=77.02, hours=24)
        assert isinstance(res, HourlyAirSeries)
        assert res.data_mode == "fixture"
        assert len(res.points) == 24
        assert res.location_cell == "28.45,77.02"

        # Points should have positive PM2.5 and local category
        assert res.points[0].pm25_ug_m3 > 0
        assert res.points[0].category_local != ""


@pytest.mark.asyncio
async def test_get_hourly_forecast_nearest_fixture_chandigarh() -> None:
    settings = Settings(google_maps_api_key=None, app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient() as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)

        # Query near Chandigarh (30.73, 76.78)
        res = await client.get_hourly_forecast(lat=30.73, lng=76.78, hours=24)
        assert res.data_mode == "fixture"
        assert len(res.points) == 24


@pytest.mark.asyncio
async def test_get_hourly_forecast_caching() -> None:
    settings = Settings(google_maps_api_key=None, app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient() as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)

        res1 = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=24)
        res2 = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=24)
        assert res1.location_cell == res2.location_cell
        # Stats should record cache hit
        assert cache.stats().hits >= 1


@pytest.mark.asyncio
async def test_get_current_conditions() -> None:
    settings = Settings(google_maps_api_key=None, app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient() as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)

        point = await client.get_current_conditions(lat=28.46, lng=77.03)
        assert point.pm25_ug_m3 > 0
        assert point.category_local != ""


@pytest.mark.asyncio
async def test_air_quality_timeout_and_breaker_failure() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    transport = httpx.MockTransport(timeout_handler)
    settings_with_key = Settings(google_maps_api_key=SecretStr("test_key"), app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AirQualityClient(settings=settings_with_key, cache=cache, http_client=http_client)
        # Should catch timeout, retry, fail, and fall back to fixture
        res = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=12)
        assert res.data_mode == "fixture"
        assert len(res.points) == 12


@pytest.mark.asyncio
async def test_demo_clock_iso_parsing() -> None:
    # Valid demo clock
    s1 = Settings(google_maps_api_key=None, demo_clock_iso="2026-11-18T10:00:00Z")
    cache1 = TTLCache(max_entries=10, default_ttl_s=60)
    async with httpx.AsyncClient() as http_client:
        c1 = AirQualityClient(settings=s1, cache=cache1, http_client=http_client)
        res1 = await c1.get_hourly_forecast(lat=28.46, lng=77.03, hours=5)
        assert res1.points[0].time_local == "10:00"

    # Invalid demo clock fallback
    s2 = Settings(google_maps_api_key=None, demo_clock_iso="invalid-date")
    cache2 = TTLCache(max_entries=10, default_ttl_s=60)
    async with httpx.AsyncClient() as http_client:
        c2 = AirQualityClient(settings=s2, cache=cache2, http_client=http_client)
        res2 = await c2.get_hourly_forecast(lat=28.46, lng=77.03, hours=5)
        assert len(res2.points) == 5
