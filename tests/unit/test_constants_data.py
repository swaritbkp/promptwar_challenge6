from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_constants_json_valid_and_complete() -> None:
    data_path = ROOT / "data" / "constants.v1.json"
    assert data_path.exists()
    with data_path.open("r", encoding="utf-8") as f:
        doc = json.load(f)

    assert doc["version"] == "v1"
    constants = doc["constants"]

    # Verify no null values in core constants
    for key, item in constants.items():
        assert "source" in item, f"Missing source in {key}"
        assert item["source"] is not None and len(item["source"]) > 5
        assert "verified" in item, f"Missing verified flag in {key}"
        assert isinstance(item["verified"], bool)
        assert "unit" in item, f"Missing unit in {key}"

        val = item["value"]
        assert val is not None, f"Null value in {key}"

        if isinstance(val, dict):
            for sub_k, sub_v in val.items():
                if isinstance(sub_v, dict):
                    for metric, metric_val in sub_v.items():
                        assert metric_val is not None, f"Null sub-metric in {key}.{sub_k}.{metric}"
                else:
                    assert sub_v is not None, f"Null sub-value in {key}.{sub_k}"

    # Verify source emission rate entries exist
    sources = constants["indoor_source_emission_rate"]["value"]
    for required_src in [
        "src_frying",
        "src_tadka",
        "src_incense_stick",
        "src_mosquito_coil",
        "src_candle",
        "src_angithi_coal",
        "src_wood_heater",
        "src_smoking",
    ]:
        assert required_src in sources
        assert sources[required_src] > 0

    # Verify emission factors exist
    efs = constants["emission_factor"]["value"]
    for required_ef in [
        "car_petrol_per_km",
        "car_diesel_per_km",
        "two_wheeler_per_km",
        "bus_per_passenger_km",
        "metro_per_passenger_km",
        "carpool_per_km_shared_3",
        "diesel_generator_per_kwh",
        "inverter_grid_per_kwh",
        "angithi_coal_per_hour",
        "electric_heater_per_hour_2kw_grid",
        "open_leaf_burning_per_kg",
    ]:
        assert required_ef in efs
        assert efs[required_ef]["kg_co2"] > 0
        assert efs[required_ef]["g_pm25"] >= 0
