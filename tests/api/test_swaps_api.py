from __future__ import annotations

from fastapi.testclient import TestClient


def test_swaps_catalogue_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/swaps/catalogue")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "swaps" in data["data"]
    assert len(data["data"]["swaps"]) >= 6


def test_swaps_impact_happy_path(client: TestClient) -> None:
    payload = {
        "swap_id": "commute_car_to_metro",
        "units_per_day": 20.0,
        "days_per_week": 5,
        "households": 250,
        "participation_rate": 0.4,
        "location": {"lat": 28.46, "lng": 77.03},
    }
    resp = client.post("/api/v1/swaps/impact", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "household" in data["data"]
    assert "community" in data["data"]
    assert data["data"]["household"]["delta_emit_daily"]["kg_co2"] < 0
    assert data["data"]["community"]["households"] == 250
    assert data["data"]["community"]["community_delta_co2_kg_monthly"] < 0
    assert data["meta"]["data_mode"] == "fixture"


def test_swaps_impact_validation_error(client: TestClient) -> None:
    # Invalid participation rate > 1.0
    payload = {
        "swap_id": "commute_car_to_metro",
        "units_per_day": 20.0,
        "participation_rate": 1.8,
    }
    resp = client.post("/api/v1/swaps/impact", json=payload)
    assert resp.status_code == 422
    err = resp.json()
    assert err["error"]["code"] == "VALIDATION_ERROR"
