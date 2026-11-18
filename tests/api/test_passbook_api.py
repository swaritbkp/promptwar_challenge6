from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hawakhata.app import create_app
from hawakhata.config import Settings


@pytest.fixture
def test_client() -> TestClient:
    settings = Settings(google_maps_api_key=None, app_env="test")
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def test_passbook_happy_path(test_client: TestClient) -> None:
    payload = {
        "profile": {
            "id": "fam_delhi",
            "name": "Delhi Household",
            "location": {"lat": 28.46, "lng": 77.03},
            "members": [
                {
                    "id": "m1",
                    "name": "Arjun",
                    "age_band": "31_41",
                    "schedule_blocks": [
                        {
                            "start_hour": 7,
                            "end_hour": 8,
                            "micro_env": "outdoor",
                            "activity": "moderate",
                            "label": "Morning Run",
                        },
                        {
                            "start_hour": 9,
                            "end_hour": 18,
                            "micro_env": "indoor_other",
                            "activity": "sedentary",
                            "label": "Office",
                        },
                    ],
                }
            ],
            "rooms": [
                {"name": "Master Bedroom", "volume_m3": 40.0, "purifier_cadr_m3_per_h": 200.0}
            ],
            "sources": [],
        }
    }
    resp = test_client.post("/api/v1/passbook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "meta" in data
    assert data["meta"]["data_mode"] == "fixture"
    assert "entries" in data["data"]
    entries = data["data"]["entries"]
    assert len(entries) == 1
    assert entries[0]["member_label"] == "Arjun"
    assert entries[0]["budget_ug"] > 0
    assert entries[0]["debit_ug"] > 0
    assert "explanation" in entries[0]


def test_passbook_validation_error(test_client: TestClient) -> None:
    # Invalid lat/lng
    payload = {
        "profile": {
            "id": "fam_bad",
            "name": "Bad",
            "location": {"lat": 999.0, "lng": 77.03},
            "members": [{"id": "m1", "name": "Arjun", "age_band": "31_41"}],
        }
    }
    resp = test_client.post("/api/v1/passbook", json=payload)
    assert resp.status_code == 422
    err = resp.json()
    assert "error" in err
    assert err["error"]["code"] == "VALIDATION_ERROR"


def test_forecast_endpoint_happy_path(test_client: TestClient) -> None:
    resp = test_client.post("/api/v1/air/forecast", json={"lat": 28.46, "lng": 77.03, "hours": 24})
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "points" in data["data"]
    assert len(data["data"]["points"]) == 24
    assert data["meta"]["data_mode"] == "fixture"
