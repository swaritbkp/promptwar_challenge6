from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import AirQualityClient, HourlyAirSeries


@pytest.mark.asyncio
async def test_live_api_mock_transport_success() -> None:
    mock_payload = {
        "hourlyForecasts": [
            {
                "dateTime": "2026-11-18T12:00:00Z",
                "indexes": [
                    {
                        "code": "ind_cpcb",
                        "aqi": 340,
                        "category": "VERY_POOR",
                        "dominantPollutant": "pm25",
                    },
                    {"code": "uaqi", "aqi": 42},
                ],
                "pollutants": [
                    {"code": "pm25", "concentration": {"value": 185.4}},
                    {"code": "pm10", "concentration": {"value": 290.0}},
                ],
                "healthRecommendations": {"generalPopulation": "Avoid"},
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Goog-Api-Key") == "test_secret_key"
        return httpx.Response(200, json=mock_payload)

    settings = Settings(google_maps_api_key=SecretStr("test_secret_key"), app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        series = await client.get_hourly_forecast(lat=28.459, lng=77.026, hours=1)
        assert isinstance(series, HourlyAirSeries) and series.data_mode == "live"
        assert len(series.points) == 1
        pt = series.points[0]
        assert pt.pm25_ug_m3 == 185.4 and pt.pm10_ug_m3 == 290.0
        assert pt.aqi_local == 340 and pt.category_local == "VERY_POOR"


@pytest.mark.asyncio
async def test_live_api_retry_and_fixture_fallback_on_500() -> None:
    calls = 0

    def error_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"error": "Internal Server Error"})

    settings = Settings(google_maps_api_key=SecretStr("test_secret_key"), app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient(transport=httpx.MockTransport(error_handler)) as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        series = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=24)
        assert calls == 2 and series.data_mode == "fixture" and len(series.points) == 24


def test_delhi_and_chandigarh_fixtures() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    for name in ["delhi_gurugram_winter.json", "chandigarh_mohali_winter.json"]:
        p = root / "data" / "fixtures" / name
        assert p.exists() and p.stat().st_size < 40_000
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data.get("synthetic") is True and "location" in data
        forecasts = data.get("hourlyForecasts", [])
        assert len(forecasts) == 96
        for point in forecasts:
            assert datetime.fromisoformat(point["dateTime"].replace("Z", "+00:00")) is not None
            indexes = {idx["code"]: idx for idx in point.get("indexes", [])}
            assert "ind_cpcb" in indexes and "uaqi" in indexes
            pollutants = {pol["code"]: pol for pol in point.get("pollutants", [])}
            assert pollutants["pm25"]["concentration"]["value"] > 0
            health = point.get("healthRecommendations", {})
            assert "generalPopulation" in health and "elderly" in health and "children" in health
