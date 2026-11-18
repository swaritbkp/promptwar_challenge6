from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_delhi_and_chandigarh_fixtures() -> None:
    fixtures_dir = ROOT / "data" / "fixtures"
    fixture_files = [
        fixtures_dir / "delhi_gurugram_winter.json",
        fixtures_dir / "chandigarh_mohali_winter.json",
    ]

    for p in fixture_files:
        assert p.exists(), f"Missing fixture file: {p}"
        size_bytes = p.stat().st_size
        assert size_bytes < 40_000, f"Fixture {p.name} is {size_bytes} bytes, must be < 40 KB"

        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data.get("synthetic") is True
        assert "location" in data
        assert "latitude" in data["location"]
        assert "longitude" in data["location"]

        forecasts = data.get("hourlyForecasts", [])
        assert len(forecasts) == 96, f"Expected 96 hourly points in {p.name}, got {len(forecasts)}"

        for i, point in enumerate(forecasts):
            assert "dateTime" in point
            dt = datetime.fromisoformat(point["dateTime"].replace("Z", "+00:00"))
            assert dt is not None

            # Indexes validation
            indexes = {idx["code"]: idx for idx in point.get("indexes", [])}
            assert "ind_cpcb" in indexes, f"Missing ind_cpcb in {p.name} point {i}"
            assert "uaqi" in indexes, f"Missing uaqi in {p.name} point {i}"
            assert indexes["ind_cpcb"]["category"] in [
                "Good",
                "Satisfactory",
                "Moderate",
                "Poor",
                "Very Poor",
                "Severe",
            ]

            # Pollutants validation
            pollutants = {pol["code"]: pol for pol in point.get("pollutants", [])}
            assert "pm25" in pollutants, f"Missing pm25 in {p.name} point {i}"
            assert "pm10" in pollutants, f"Missing pm10 in {p.name} point {i}"
            pm25_val = pollutants["pm25"]["concentration"]["value"]
            pm10_val = pollutants["pm10"]["concentration"]["value"]
            assert pm25_val > 0, f"PM2.5 must be positive in {p.name} point {i}"
            assert pm10_val >= pm25_val, f"PM10 must be >= PM2.5 in {p.name} point {i}"

            # Health recommendations validation
            health = point.get("healthRecommendations", {})
            assert "generalPopulation" in health
            assert "elderly" in health
            assert "children" in health
