"""Open-Meteo primary AQ provider: parsing, pass-through, provider chain, cache, offline tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import (
    IST,
    OPEN_METEO_AQ_URL,
    AirQualityClient,
    CircuitBreaker,
    HourlyAirSeries,
    clock_aligned_pm25,
    parse_open_meteo_hourly,
)


def _payload(start: datetime, pm25: list[float | None], pm10: list[float | None]) -> dict[str, Any]:
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(len(pm25))]
    return {"hourly": {"time": times, "pm2_5": pm25, "pm10": pm10}}


def _now_hour() -> datetime:
    return datetime.now(IST).replace(minute=0, second=0, microsecond=0, tzinfo=None)


def test_parse_starts_at_current_hour_and_passes_values_unmodified() -> None:
    now = datetime(2026, 11, 20, 18, 30, tzinfo=IST)
    start = datetime(2026, 11, 20, 0, 0)
    pm25 = [float(100 + i) for i in range(48)]
    pm10 = [float(200 + i) for i in range(48)]
    pts = parse_open_meteo_hourly(_payload(start, pm25, pm10), hours=24, now_ist=now)
    assert len(pts) == 24
    assert pts[0].time_local == "18:00" and pts[0].pm25_ug_m3 == 118.0
    assert pts[0].pm10_ug_m3 == 218.0  # PM10 surfaced, untouched
    assert pts[0].time_utc == "2026-11-20T12:30:00Z"
    assert pts[-1].time_local == "17:00"


def test_parse_carries_forward_missing_hours_and_rejects_empty() -> None:
    now = datetime(2026, 11, 20, 0, 0, tzinfo=IST)
    start = datetime(2026, 11, 20, 0, 0)
    pts = parse_open_meteo_hourly(
        _payload(start, [None, 150.0, None, 90.0], [None, 160.0, None, None]), 4, now
    )
    assert [p.pm25_ug_m3 for p in pts] == [150.0, 150.0, 90.0]
    assert pts[1].pm10_ug_m3 is None
    with pytest.raises(ValueError, match=r"no PM2\.5"):
        parse_open_meteo_hourly(_payload(start, [None, None], [None, None]), 2, now)


def _client(
    handler: Any, app_env: str = "dev", key: str | None = None
) -> tuple[AirQualityClient, TTLCache]:
    cache = TTLCache(max_entries=64, default_ttl_s=600)
    s = Settings(_env_file=None, app_env=app_env, google_maps_api_key=key)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AirQualityClient(s, cache, http, breaker=CircuitBreaker(failure_threshold=1)), cache


@pytest.mark.asyncio
async def test_open_meteo_is_primary_live_provider_with_pm10_and_freshness() -> None:
    seen: list[httpx.Request] = []
    pm25 = [float(300 - i) for i in range(120)]
    pm10 = [float(400 - i) for i in range(120)]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_payload(_now_hour(), pm25, pm10))

    client, _ = _client(handler, key="g-key")
    series = await client.get_hourly_forecast(lat=28.45923, lng=77.02664, hours=96)
    assert isinstance(series, HourlyAirSeries)
    assert series.provider == "open_meteo_live" and series.data_mode == "live"
    assert series.data_source == "Open-Meteo Live AQ"
    assert len(series.points) == 96
    # Live data passes through unmodified (no city scaling, no synoptic modifiers).
    assert [p.pm25_ug_m3 for p in series.points[:3]] == [300.0, 299.0, 298.0]
    assert series.points[0].pm10_ug_m3 == 400.0
    assert series.fetched_at_ist.endswith(" IST") and len(series.fetched_at_ist) == 9
    # Exactly one upstream call, to Open-Meteo, with privacy-rounded coordinates.
    assert len(seen) == 1 and str(seen[0].url).startswith(OPEN_METEO_AQ_URL)
    q = seen[0].url.params
    assert q["latitude"] == "28.46" and q["longitude"] == "77.03"
    assert q["hourly"] == "pm2_5,pm10" and q["timezone"] == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_cache_shares_one_upstream_call_across_horizons() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_payload(_now_hour(), [120.0] * 120, [130.0] * 120))

    client, _ = _client(handler)
    s96 = await client.get_hourly_forecast(lat=19.07, lng=72.87, hours=96)
    s24 = await client.get_hourly_forecast(lat=19.07, lng=72.87, hours=24)
    assert len(s96.points) == 96 and len(s24.points) == 24 and calls == 1
    assert s24.provider == "open_meteo_live"


@pytest.mark.asyncio
async def test_open_meteo_failure_without_key_falls_back_to_fixture() -> None:
    client, _ = _client(lambda _r: httpx.Response(502))
    series = await client.get_hourly_forecast(lat=26.91, lng=75.78, hours=24)
    assert series.provider == "fixture" and series.data_mode == "fixture"
    assert series.data_source == "Offline Synthetic Fixture" and len(series.points) == 24


@pytest.mark.asyncio
async def test_malformed_open_meteo_payload_falls_back() -> None:
    client, _ = _client(lambda _r: httpx.Response(200, json={"hourly": {"time": []}}))
    series = await client.get_hourly_forecast(lat=25.59, lng=85.13, hours=24)
    assert series.provider == "fixture"


@pytest.mark.asyncio
async def test_test_env_never_touches_network() -> None:
    def boom(_r: httpx.Request) -> httpx.Response:
        raise AssertionError("network call in app_env=test")

    client, _ = _client(boom, app_env="test", key="g-key")
    series = await client.get_hourly_forecast(lat=28.46, lng=77.03, hours=96)
    assert series.provider == "fixture" and len(series.points) == 96


def test_start_hour_and_clock_alignment() -> None:
    now = datetime(2026, 11, 20, 18, 0, tzinfo=IST)
    start = datetime(2026, 11, 20, 18, 0)
    pts = parse_open_meteo_hourly(
        _payload(start, [float(h) for h in range(24)], [None] * 24), 24, now
    )
    series = HourlyAirSeries(pts, "x", "live", "2026-11-20T13:00:00+00:00", "open_meteo_live")
    assert series.start_hour == 18 and series.fetched_at_ist == "18:30 IST"
    aligned = clock_aligned_pm25(series, 24)
    # Index 18 (clock 18:00) holds the first reading; index 6 (06:00) the 13th.
    assert aligned[18] == 0.0 and aligned[6] == 12.0 and aligned[17] == 23.0
