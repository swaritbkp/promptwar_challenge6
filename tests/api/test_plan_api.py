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


def test_plan_endpoint_happy_path(test_client: TestClient) -> None:
    payload = {
        "profile": {
            "id": "fam_delhi",
            "name": "Delhi Household",
            "location": {"lat": 28.46, "lng": 77.03},
            "members": [
                {
                    "id": "m1",
                    "name": "Grandpa",
                    "age_band": "61_71",
                    "schedule_blocks": [
                        {
                            "start_hour": 10,
                            "end_hour": 13,
                            "micro_env": "indoor_other",
                            "activity": "sedentary",
                            "label": "Reading",
                        }
                    ],
                }
            ],
            "rooms": [],
            "sources": [],
        },
        "member_id": "m1",
        "flexible_activities": [
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
        ],
    }
    resp = test_client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "shifts" in data["data"]
    assert len(data["data"]["shifts"]) == 1
    shift = data["data"]["shifts"][0]
    assert shift["activity_id"] == "walk"
    assert "optimized_start_hour" in shift
    assert data["meta"]["data_mode"] == "fixture"


def test_plan_endpoint_member_not_found(test_client: TestClient) -> None:
    payload = {
        "profile": {
            "id": "fam_delhi",
            "name": "Delhi Household",
            "location": {"lat": 28.46, "lng": 77.03},
            "members": [
                {"id": "m1", "name": "Grandpa", "age_band": "61_71", "schedule_blocks": []}
            ],
            "rooms": [],
            "sources": [],
        },
        "member_id": "non_existent_member",
        "flexible_activities": [],
    }
    resp = test_client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 404
    err = resp.json()
    assert "error" in err
    assert err["error"]["code"] == "NOT_FOUND"


def test_plan_endpoint_with_indoor_simulation(test_client: TestClient) -> None:
    payload = {
        "profile": {
            "id": "fam_rooms",
            "name": "Household With Rooms",
            "location": {"lat": 28.46, "lng": 77.03},
            "members": [
                {
                    "id": "m1",
                    "name": "Arjun",
                    "age_band": "31_41",
                    "schedule_blocks": [],
                }
            ],
            "rooms": [
                {
                    "name": "Living Room",
                    "volume_m3": 50.0,
                    "purifier_cadr_m3_per_h": 200.0,
                    "windows_open_hours": [14],
                    "purifier_on_hours": [22, 23],
                }
            ],
            "sources": [{"kind": "src_frying", "start_hour": 12, "minutes": 30.0}],
        },
        "member_id": "m1",
        "flexible_activities": [
            {
                "id": "run",
                "member_id": "m1",
                "title": "Evening Run",
                "duration_hours": 1,
                "earliest_start_hour": 16,
                "latest_start_hour": 20,
                "micro_env": "outdoor",
                "activity": "vigorous",
                "usual_start_hour": 18,
            }
        ],
    }
    resp = test_client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["data_mode"] == "fixture"
    assert len(data["data"]["shifts"]) == 1
