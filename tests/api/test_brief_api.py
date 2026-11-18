from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from hawakhata.app import create_app
from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import AirQualityClient, HourlyAirSeries
from hawakhata.services.brief_service import (
    BriefResult,
    detect_forecast_shift,
    generate_morning_brief,
    replan_if_needed,
)


def _sample_profile(sensitivities: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": "fam_delhi",
        "name": "Delhi Household",
        "location": {"lat": 28.46, "lng": 77.03},
        "rooms": [{"name": "Living Room", "volume_m3": 50.0}],
        "sources": [],
        "members": [
            {
                "id": "m1",
                "name": "Riya",
                "age_band": "child",
                "sensitivities": sensitivities or ["asthma"],
                "schedule_blocks": [
                    {
                        "activity": "outdoor_play",
                        "start_hour": 7,
                        "end_hour": 8,
                        "micro_env": "outdoor",
                        "flexible": True,
                        "earliest_start": 6,
                        "latest_end": 18,
                    }
                ],
            }
        ],
    }


def test_detect_forecast_shift() -> None:
    old = [100.0, 120.0, 150.0, 130.0]
    assert detect_forecast_shift(old, [105.0, 125.0, 155.0, 135.0], threshold_ug_m3=40.0) is False
    assert detect_forecast_shift(old, [100.0, 120.0, 195.0, 130.0], threshold_ug_m3=40.0) is True
    assert detect_forecast_shift([], [50.0], threshold_ug_m3=40.0) is False


def test_replan_if_needed() -> None:
    old_series = [100.0] * 24
    new_series = [100.0] * 24
    new_series[7] = 200.0
    res = replan_if_needed(_sample_profile(), old_series, new_series, threshold_ug_m3=40.0)
    assert res.shifted is True and res.replanned is True and len(res.replan_notes) > 0

    no_flex = {
        "id": "f",
        "members": [{"id": "m", "name": "Adult", "age_band": "adult", "schedule_blocks": []}],
    }
    assert len(replan_if_needed(no_flex, old_series, new_series).replan_notes) == 1


@pytest.mark.asyncio
async def test_generate_morning_brief_service() -> None:
    settings = Settings(app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient() as http_client:
        client = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        series = await client.get_hourly_forecast(lat=28.459, lng=77.026, hours=24)

    brief = generate_morning_brief(_sample_profile(), series)
    assert isinstance(brief, BriefResult)
    assert 0 < brief.cleanest_pm25 <= brief.worst_pm25
    assert len(brief.top_actions) <= 3 and len(brief.sensitive_member_alerts) > 0


def test_brief_endpoint_success() -> None:
    with TestClient(create_app()) as client:
        payload = {"profile": _sample_profile(), "previous_forecast_pm25": [100.0] * 24}
        resp = client.post("/api/v1/brief", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body and body["meta"]["data_mode"] in ("live", "fixture")
        assert "worst_hour_local" in body["data"] and "cleanest_window_local" in body["data"]


def test_brief_empty_series() -> None:
    empty = HourlyAirSeries(
        points=[], location_cell="0.0,0.0", data_mode="fixture", fetched_at="2026-01-15T00:00:00Z"
    )
    brief = generate_morning_brief({"id": "fam", "members": []}, empty)
    assert brief.worst_pm25 == 0.0 and len(brief.top_actions) == 0
