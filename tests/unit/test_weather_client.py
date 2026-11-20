"""Unit tests for Open-Meteo weather client and synthetic fallback."""

from __future__ import annotations

import httpx
import pytest

from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import CircuitBreaker, CircuitState
from hawakhata.integrations.weather import (
    WeatherClient,
    generate_synthetic_winter_weather,
)


def test_synthetic_weather_generation() -> None:
    s = generate_synthetic_winter_weather(28.4595, 77.0266, hours=96)
    assert len(s.points) == 96 and s.location_cell == "28.46,77.03" and s.data_mode == "fixture"
    tod_14, tod_05 = s.points[14], s.points[5]
    assert tod_14.temperature_c > tod_05.temperature_c
    assert tod_14.boundary_layer_height_m >= 800.0 and tod_05.boundary_layer_height_m <= 350.0


@pytest.mark.asyncio
async def test_weather_client_test_mode_and_caching() -> None:
    cache = TTLCache(max_entries=64, default_ttl_s=300)
    async with httpx.AsyncClient() as http:
        client = WeatherClient(Settings(app_env="test"), cache, http)
        r1 = await client.get_hourly_weather(28.4595, 77.0266, hours=96)
        r2 = await client.get_hourly_weather(28.4595, 77.0266, hours=96)
        assert len(r1.points) == 96 and r1.data_mode == "fixture" and len(r2.points) == 96


@pytest.mark.asyncio
async def test_weather_client_live_mock_and_circuit_breaker() -> None:
    payload = {
        "hourly": {
            "time": ["2099-01-01T00:00"],
            "temperature_2m": [15.0],
            "relative_humidity_2m": [75.0],
            "wind_speed_10m": [6.0],
            "precipitation": [0.0],
            "boundary_layer_height": [220.0],
        }
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http:
        client = WeatherClient(Settings(app_env="dev"), TTLCache(64, 300), http)
        res = await client.get_hourly_weather(28.4595, 77.0266, hours=1)
        assert res.data_mode == "live" and res.points[0].temperature_c == 15.0

    breaker = CircuitBreaker(failure_threshold=1, recovery_time_s=60.0)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    ) as http_err:
        err_client = WeatherClient(
            Settings(app_env="dev"), TTLCache(64, 300), http_err, breaker=breaker
        )
        fb1 = await err_client.get_hourly_weather(28.4595, 77.0266, hours=24)
        assert fb1.data_mode == "fixture" and breaker.state == CircuitState.OPEN
        fb2 = await err_client.get_hourly_weather(28.4595, 77.0266, hours=24)
        assert fb2.data_mode == "fixture"
