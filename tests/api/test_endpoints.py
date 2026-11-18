from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from hawakhata.app import create_app
from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.core.errors import NotFoundError
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.services import story_service
from hawakhata.services.brief_service import (
    BriefResult,
    detect_forecast_shift,
    generate_morning_brief,
    replan_if_needed,
)


def _flex_act() -> list[dict[str, Any]]:
    return [
        {
            "id": "walk",
            "member_id": "m1",
            "title": "Morning Walk",
            "duration_hours": 1,
            "earliest_start_hour": 6,
            "latest_start_hour": 18,
            "micro_env": "outdoor",
            "activity": "moderate",
            "usual_start_hour": 7,
        }
    ]


def test_passbook_endpoint(client: TestClient, sample_profile_data: dict[str, Any]) -> None:
    resp = client.post("/api/v1/passbook", json={"profile": sample_profile_data})
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["data_mode"] == "fixture"
    entries = data["data"]["entries"]
    assert len(entries) == 1
    assert entries[0]["member_label"] == "Arjun"
    assert entries[0]["budget_ug"] > 0 and entries[0]["debit_ug"] > 0

    bad = {
        "profile": {
            "id": "fam_bad",
            "name": "Bad",
            "location": {"lat": 999.0, "lng": 77.03},
            "members": [{"id": "m1", "name": "Arjun", "age_band": "31_41"}],
        }
    }
    assert client.post("/api/v1/passbook", json=bad).status_code == 422


def test_forecast_endpoint(client: TestClient) -> None:
    resp = client.post("/api/v1/air/forecast", json={"lat": 28.46, "lng": 77.03, "hours": 24})
    assert resp.status_code == 200
    assert len(resp.json()["data"]["points"]) == 24


def test_plan_endpoint(client: TestClient, sample_profile_data: dict[str, Any]) -> None:
    payload = {
        "profile": sample_profile_data,
        "member_id": "m1",
        "flexible_activities": _flex_act(),
    }
    resp = client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["shifts"]) == 1

    bad_member = dict(payload)
    bad_member["member_id"] = "nonexistent"
    assert client.post("/api/v1/plan", json=bad_member).status_code == 404

    empty_acts = dict(payload)
    empty_acts["flexible_activities"] = []
    assert client.post("/api/v1/plan", json=empty_acts).status_code == 200


def test_indoor_simulate_endpoint(client: TestClient) -> None:
    payload = {
        "room": {
            "name": "Master Bedroom",
            "volume_m3": 45.0,
            "purifier_cadr_m3_per_h": 150.0,
            "windows_open_hours": [14, 15],
            "purifier_on_hours": [22, 23, 0, 1, 2, 3, 4, 5],
        },
        "sources": [
            {"kind": "src_frying", "start_hour": 12, "minutes": 25.0, "count": 1},
        ],
        "location": {"lat": 28.46, "lng": 77.03},
    }
    resp = client.post("/api/v1/indoor/simulate", json=payload)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["simulation"]["hourly_pm25_ug_m3"]) == 24

    bad = dict(payload)
    bad["room"] = {"name": "Bad", "volume_m3": 2.0}
    assert client.post("/api/v1/indoor/simulate", json=bad).status_code == 422


def test_swaps_endpoints(client: TestClient) -> None:
    cat_resp = client.get("/api/v1/swaps/catalogue")
    assert cat_resp.status_code == 200 and len(cat_resp.json()["data"]["swaps"]) >= 6

    payload = {
        "swap_id": "commute_car_to_metro",
        "units_per_day": 20.0,
        "days_per_week": 5,
        "households": 250,
        "participation_rate": 0.4,
        "location": {"lat": 28.46, "lng": 77.03},
    }
    impact_resp = client.post("/api/v1/swaps/impact", json=payload)
    assert impact_resp.status_code == 200
    assert impact_resp.json()["data"]["household"]["delta_emit_daily"]["kg_co2"] < 0

    bad = dict(payload)
    bad["participation_rate"] = 1.5
    assert client.post("/api/v1/swaps/impact", json=bad).status_code == 422


def test_demo_and_story_endpoints(client: TestClient) -> None:
    p_resp = client.get("/api/v1/demo/profiles")
    assert p_resp.status_code == 200 and "demo_ncr" in p_resp.json()["data"]

    s_ncr = client.get("/api/v1/story/ncr")
    assert s_ncr.status_code == 200 and s_ncr.json()["data"]["story_id"] == "ncr"

    s_chd = client.get("/api/v1/story/chd")
    assert s_chd.status_code == 200 and s_chd.json()["data"]["story_id"] == "chd"

    assert client.get("/api/v1/story/nonexistent").status_code == 404


def test_story_service_missing_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(story_service, "_PROFILES_PATH", Path("/nonexistent/profiles.json"))
    assert story_service.load_demo_profiles() == {}

    monkeypatch.setattr(story_service, "_STORY_PATH", Path("/nonexistent/story.json"))
    with pytest.raises(NotFoundError, match="Story configuration file missing"):
        story_service.load_story("ncr")


def test_brief_service_and_endpoint(sample_profile_data: dict[str, Any]) -> None:
    assert detect_forecast_shift([100.0], [150.0], threshold_ug_m3=40.0) is True
    assert detect_forecast_shift([100.0], [120.0], threshold_ug_m3=40.0) is False

    replan = replan_if_needed(sample_profile_data, [100.0] * 24, [200.0] * 24, threshold_ug_m3=40.0)
    assert replan.shifted is True and len(replan.replan_notes) > 0

    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/v1/brief",
            json={"profile": sample_profile_data, "previous_forecast_pm25": [100.0] * 24},
        )
        assert resp.status_code == 200
        assert "headline" in resp.json()["data"]


@pytest.mark.asyncio
async def test_generate_morning_brief_async(sample_profile_data: dict[str, Any]) -> None:
    settings = Settings(app_env="test")
    cache = TTLCache(max_entries=100, default_ttl_s=3600)
    async with httpx.AsyncClient() as http_client:
        aq = AirQualityClient(settings=settings, cache=cache, http_client=http_client)
        series = await aq.get_hourly_forecast(lat=28.459, lng=77.026, hours=24)

    brief = generate_morning_brief(sample_profile_data, series)
    assert isinstance(brief, BriefResult)
    assert 0 < brief.cleanest_pm25 <= brief.worst_pm25
