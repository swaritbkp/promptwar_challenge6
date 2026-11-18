from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import (
    AirQualityClient,
    HourlyAirSeries,
)


@pytest.mark.asyncio
async def test_live_api_mock_transport_success() -> None:
    # Sample mock response matching Google Maps Air Quality API
    mock_payload = {
        "hourlyForecasts": [
            {
                "dateTime": "2026-11-18T12:00:00Z",
                "indexes": [
                    {
                        "code": "ind_cpcb",
                        "displayName": "CPCB NAQI",
                        "aqi": 340,
                        "category": "VERY_POOR",
                        "dominantPollutant": "pm25",
                        "color": {"red": 0.8, "green": 0.1, "blue": 0.1},
                    },
                    {
                        "code": "uaqi",
                        "displayName": "Universal AQI",
                        "aqi": 42,
                        "category": "Poor air quality",
                        "dominantPollutant": "pm25",
                    },
                ],
                "pollutants": [
                    {
                        "code": "pm25",
                        "displayName": "PM2.5",
                        "concentration": {
                            "value": 185.4,
                            "units": "MICROGRAMS_PER_CUBIC_METER",
                        },
                    },
                    {
                        "code": "pm10",
                        "displayName": "PM10",
                        "concentration": {
                            "value": 290.0,
                            "units": "MICROGRAMS_PER_CUBIC_METER",
                        },
                    },
                ],
                "healthRecommendations": {
                    "generalPopulation": "Avoid prolonged outdoor exposure.",
                    "elderly": "Remain indoors with air filtration.",
                    "children": "Avoid outdoor play activities.",
                },
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Goog-Api-Key") == "test_secret_key"
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    settings = Settings(
        google_maps_api_key=SecretStr("test_secret_key"),
        app_env="test",
    )
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        series = await client.get_hourly_forecast(lat=28.459, lng=77.026, hours=1)
        assert isinstance(series, HourlyAirSeries)
        assert series.data_mode == "live"
        assert len(series.points) == 1
        pt = series.points[0]
        assert pt.pm25_ug_m3 == 185.4
        assert pt.pm10_ug_m3 == 290.0
        assert pt.aqi_local == 340
        assert pt.category_local == "VERY_POOR"
        assert pt.dominant_pollutant == "pm25"
        assert "generalPopulation" in pt.health_recs


@pytest.mark.asyncio
async def test_live_api_retry_and_fixture_fallback_on_500() -> None:
    calls = 0

    def error_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"error": "Internal Server Error"})

    transport = httpx.MockTransport(error_handler)
    settings = Settings(
        google_maps_api_key=SecretStr("test_secret_key"),
        app_env="test",
    )
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        # Should attempt retry (calls == 2), fail, and fall back cleanly to fixture without raising
        series = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=24)
        assert calls == 2  # initial + 1 retry
        assert series.data_mode == "fixture"
        assert len(series.points) == 24
