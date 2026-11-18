from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


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


def test_plan_endpoint_happy_path(client: TestClient, sample_profile_data: dict[str, Any]) -> None:
    payload = {
        "profile": sample_profile_data,
        "member_id": "m1",
        "flexible_activities": _flex_act(),
    }
    resp = client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data and "shifts" in data["data"]
    assert len(data["data"]["shifts"]) == 1
    shift = data["data"]["shifts"][0]
    assert shift["activity_id"] == "walk" and "optimized_start_hour" in shift
    assert data["meta"]["data_mode"] == "fixture"


def test_plan_endpoint_member_not_found(
    client: TestClient, sample_profile_data: dict[str, Any]
) -> None:
    payload = {
        "profile": sample_profile_data,
        "member_id": "nonexistent_member",
        "flexible_activities": _flex_act(),
    }
    resp = client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 404
    err = resp.json()
    assert "error" in err and err["error"]["code"] == "NOT_FOUND"


def test_plan_endpoint_empty_flexible_activities(
    client: TestClient, sample_profile_data: dict[str, Any]
) -> None:
    payload = {
        "profile": sample_profile_data,
        "member_id": "m1",
        "flexible_activities": [],
    }
    resp = client.post("/api/v1/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["shifts"] == [] and data["total_savings_ug"] == 0.0
