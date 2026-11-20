"""API tests: source/PM10/GRAP/3-slot fields, mask endpoint, India search, personas, chat."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hawakhata.app import create_app
from hawakhata.config import Settings

LOC = {"lat": 28.4595, "lng": 77.0266, "city_name": "Gurugram"}
PROFILE: dict[str, Any] = {
    "id": "fam",
    "name": "Family",
    "location": LOC,
    "members": [
        {"id": "m1", "name": "Aarav", "age_band": "child", "sensitivities": ["asthma"]},
        {"id": "m2", "name": "Dadi", "age_band": "senior", "sensitivities": []},
    ],
}


@pytest.fixture
def api() -> Iterator[TestClient]:
    s = Settings(_env_file=None, app_env="test", rate_limit_per_min=500, ai_limit_per_min=50)
    with TestClient(create_app(s)) as c:
        yield c


def test_four_day_exposes_source_pm10_grap_and_day_parts(api: TestClient) -> None:
    body = api.get("/api/v1/forecast/4day", params={"lat": 28.4595, "lng": 77.0266}).json()
    d = body["data"]
    assert d["data_mode"] == "fixture" and d["data_source"] == "Offline Synthetic Fixture"
    assert "current_pm10" in d and d["current_pm25"] > 0  # fixture PM10 may be null
    assert d["fetched_at_ist"].endswith(" IST")
    assert d["grap"]["stage"] in range(5) and d["grap"]["advisories_hi"]
    assert [p["part"] for p in d["day_parts"]] == ["morning", "afternoon", "evening"]
    assert len(d["hourly_pm25_24h"]) == 24
    for day in d["days"]:
        start = int(day["cleanest_window_start"][:2])
        assert 6 <= start <= 17  # waking window 06:00-20:00 on true clock hours
    assert body["meta"]["data_mode"] == "fixture"


def test_passbook_shares_live_snapshot_with_four_day(api: TestClient) -> None:
    pb = api.post("/api/v1/passbook", json={"profile": PROFILE}).json()["data"]
    fd = api.get("/api/v1/forecast/4day", params={"lat": 28.4595, "lng": 77.0266}).json()["data"]
    for key in ("current_pm25", "current_pm10", "current_aqi", "data_source", "fetched_at_ist"):
        assert pb[key] == fd[key], key
    assert pb["grap"]["code"] == fd["grap"]["code"] and pb["entries"]


def test_mask_endpoint_recalculates_dose_and_budget(api: TestClient) -> None:
    base = {
        "location": LOC,
        "age_band": "senior",
        "activity": "walk",
        "duration_min": 60,
        "start_hour": 7,
    }
    res = {
        m: api.post("/api/v1/exposure/activity", json={**base, "mask": m}).json()["data"]
        for m in ("none", "surgical", "n95")
    }
    assert (
        res["none"]["masked_dose_ug"]
        > res["surgical"]["masked_dose_ug"]
        > res["n95"]["masked_dose_ug"]
    )
    assert res["n95"]["filtration_factor"] == 0.15 and res["surgical"]["filtration_factor"] == 0.65
    assert res["n95"]["mask_saved_ug"] > 0 and res["none"]["mask_saved_ug"] == 0
    assert res["none"]["budget_ug"] == res["n95"]["budget_ug"] > 0
    assert res["n95"]["explanation"]["formula"].startswith("dose_ug")
    bad = api.post("/api/v1/exposure/activity", json={**base, "mask": "cloth"})
    assert bad.status_code == 422


def test_location_search_offline_fallback_and_validation(api: TestClient) -> None:
    body = api.get("/api/v1/locations/search", params={"q": "Jaipur"}).json()
    assert body["data"][0]["name"] == "Jaipur" and body["data"][0]["source"] == "builtin"
    assert body["meta"]["data_mode"] == "fixture"
    assert api.get("/api/v1/locations/search", params={"q": "लखनऊ"}).status_code == 200
    for bad in ("<script>", "a", "x" * 61, "Pune; DROP"):
        assert api.get("/api/v1/locations/search", params={"q": bad}).status_code == 422


def test_personas_endpoint_returns_four_scenarios(api: TestClient) -> None:
    personas = api.get("/api/v1/demo/personas").json()["data"]["personas"]
    assert [p["id"] for p in personas] == [
        "delhi_family",
        "mumbai_commuter",
        "kolkata_athlete",
        "chandigarh_senior_pets",
    ]
    for p in personas:
        pb = api.post(
            "/api/v1/passbook",
            json={
                "profile": {
                    "id": p["id"],
                    "name": "x",
                    "location": p["location"],
                    "members": p["members"],
                }
            },
        )
        assert pb.status_code == 200 and len(pb.json()["data"]["entries"]) == len(p["members"])


def test_pet_guidance_uses_current_hour(api: TestClient) -> None:
    d = api.post("/api/v1/pets/guidance", json={"species": "bird", "location": LOC}).json()["data"]
    fd = api.get("/api/v1/forecast/4day", params={"lat": 28.4595, "lng": 77.0266}).json()["data"]
    assert round(d["current_pm25"], 1) == fd["current_pm25"]


def _chat(api: TestClient, msg: str) -> dict[str, Any]:
    r = api.post("/api/v1/chat", json={"message": msg, "profile": PROFILE})
    assert r.status_code == 200
    return dict(r.json()["data"])


def test_chat_7am_vs_4pm_direct_comparison(api: TestClient) -> None:
    d = _chat(api, "Is it safe for Dadi to walk at 7 AM or 4 PM today?")
    assert d["follow_up"] is None and d["chips"] == []
    assert "07:00" in d["reply"] and "16:00" in d["reply"] and "Dadi" in d["reply"]
    assert "µg/m³" in d["reply"] and "AQI" in d["reply"] and "µg" in d["reply"]
    assert d["grounded"] is True and d["numbers_used"]


@pytest.mark.parametrize(
    "msg",
    [
        "What inhaler dose should my child take today?",
        "How many puffs of salbutamol for my 6-year-old?",
        "Salbutamol dose for my son?",
    ],
)
def test_chat_standalone_medical_dosing_is_refused(api: TestClient, msg: str) -> None:
    d = _chat(api, msg)
    assert "not medical advice or prescriptions" in d["reply"]
    assert "consult a certified medical doctor" in d["reply"]
    assert "µg" not in d["reply"] and "AQI" not in d["reply"]  # no air-quality advice
    assert "Request blocked" not in d["reply"]  # not mistaken for prompt injection
    assert d["tool_calls"] == []
