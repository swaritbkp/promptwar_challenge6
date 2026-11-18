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


def test_indoor_simulate_happy_path(test_client: TestClient) -> None:
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
            {"kind": "src_incense_stick", "start_hour": 7, "minutes": 30.0, "count": 2},
        ],
        "location": {"lat": 28.46, "lng": 77.03},
    }
    resp = test_client.post("/api/v1/indoor/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "simulation" in data["data"]
    assert "purifier_recommendation" in data["data"]
    assert "ventilation_recommendation" in data["data"]
    assert "ranked_hacks" in data["data"]
    assert len(data["data"]["simulation"]["hourly_pm25_ug_m3"]) == 24
    assert data["meta"]["data_mode"] == "fixture"


def test_indoor_simulate_validation_error(test_client: TestClient) -> None:
    # Volume must be >= 5.0
    payload = {
        "room": {
            "name": "Impossible Room",
            "volume_m3": 2.0,
            "purifier_cadr_m3_per_h": 0.0,
        },
        "sources": [],
        "location": {"lat": 28.46, "lng": 77.03},
    }
    resp = test_client.post("/api/v1/indoor/simulate", json=payload)
    assert resp.status_code == 422
    err = resp.json()
    assert err["error"]["code"] == "VALIDATION_ERROR"
