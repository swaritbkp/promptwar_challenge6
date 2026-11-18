from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def test_passbook_happy_path(client: TestClient, sample_profile_data: dict[str, Any]) -> None:
    resp = client.post("/api/v1/passbook", json={"profile": sample_profile_data})
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["data_mode"] == "fixture"
    entries = data["data"]["entries"]
    assert len(entries) == 1
    assert entries[0]["member_label"] == "Arjun"
    assert entries[0]["budget_ug"] > 0 and entries[0]["debit_ug"] > 0
    assert "explanation" in entries[0]


def test_passbook_validation_error(client: TestClient) -> None:
    payload = {
        "profile": {
            "id": "fam_bad",
            "name": "Bad",
            "location": {"lat": 999.0, "lng": 77.03},
            "members": [{"id": "m1", "name": "Arjun", "age_band": "31_41"}],
        }
    }
    resp = client.post("/api/v1/passbook", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_forecast_endpoint_happy_path(client: TestClient) -> None:
    resp = client.post("/api/v1/air/forecast", json={"lat": 28.46, "lng": 77.03, "hours": 24})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]["points"]) == 24
    assert data["meta"]["data_mode"] == "fixture"
