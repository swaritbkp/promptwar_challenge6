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
    idx = [
        {"code": "ind_cpcb", "aqi": 340, "category": "VERY_POOR", "dominantPollutant": "pm25"},
        {"code": "uaqi", "aqi": 42},
    ]
    pol = [
        {"code": "pm25", "concentration": {"value": 185.4}},
        {"code": "pm10", "concentration": {"value": 290.0}},
    ]
    mock_payload = {
        "hourlyForecasts": [
            {
                "dateTime": "2026-11-18T12:00:00Z",
                "indexes": idx,
                "pollutants": pol,
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
        return httpx.Response(500, json={"error": "server error"})

    settings = Settings(google_maps_api_key=SecretStr("test_key"), app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient(transport=httpx.MockTransport(error_handler)) as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        series = await client.get_hourly_forecast(lat=28.459, lng=77.026, hours=2)
        assert isinstance(series, HourlyAirSeries) and series.data_mode == "fixture"
        assert len(series.points) == 2 and calls == 2


def test_fixtures_contract_delhi_and_chandigarh() -> None:
    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"
    for name in ("delhi_gurugram_winter.json", "chandigarh_mohali_winter.json"):
        path = fixtures_dir / name
        assert path.exists() and path.stat().st_size <= 40_000
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        forecasts = data.get("hourlyForecasts", [])
        assert len(forecasts) >= 24
        sample = forecasts[0]
        assert "dateTime" in sample and "indexes" in sample and "pollutants" in sample
        assert datetime.fromisoformat(sample["dateTime"].replace("Z", "+00:00"))
        ind_idx = next(
            (idx for idx in sample["indexes"] if idx.get("code") in ("ind_cpcb", "cpcb")), None
        )
        assert ind_idx is not None and ind_idx.get("aqi") is not None
