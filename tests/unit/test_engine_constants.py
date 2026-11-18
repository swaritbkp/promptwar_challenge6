from __future__ import annotations

import json
from pathlib import Path

import pytest

from hawakhata.core.errors import ValidationFailedError
from hawakhata.engine.constants import get_constant, load_constants
from hawakhata.engine.explain import Explanation


def test_load_constants_schema() -> None:
    constants = load_constants()
    assert "who_aqg_pm25_24h" in constants
    c = constants["who_aqg_pm25_24h"]
    assert c.value == 15
    assert c.unit == "ug_m3"
    assert c.source != ""
    assert c.verified is True


def test_get_constant_success_and_missing() -> None:
    c = get_constant("who_aqg_pm25_24h")
    assert c.id == "who_aqg_pm25_24h"
    assert c.value == 15

    with pytest.raises(KeyError, match="Unknown constant id"):
        get_constant("non_existent_constant_id_123")


def test_load_constants_errors(tmp_path: Path) -> None:
    # Non-existent file
    with pytest.raises(ValidationFailedError, match="not found"):
        load_constants(Path("/non/existent/path/constants.json"))

    # Invalid JSON
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("not json", encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="Failed to parse"):
        load_constants(bad_json)

    # Missing root constants key
    empty_obj = tmp_path / "empty.json"
    empty_obj.write_text('{"foo": "bar"}', encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="root 'constants' mapping"):
        load_constants(empty_obj)

    # Invalid entry
    bad_entry = tmp_path / "bad_entry.json"
    bad_entry.write_text('{"constants": {"k": "not a dict"}}', encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="invalid schema"):
        load_constants(bad_entry)


def test_explanation_frozen_and_serializable() -> None:
    exp = Explanation(
        formula="debit = sum(C_i * IR_i * t_i)",
        inputs={"C_avg": "150 ug/m3", "IR_mean": "16.0 m3/day"},
        constants_used=["who_aqg_pm25_24h", "inhalation_rate_daily_mean"],
        sources=["WHO 2021", "US EPA 2011"],
        assumptions=["Uniform hourly distribution during sleep"],
    )
    with pytest.raises(AttributeError):
        # type: ignore[misc]
        exp.formula = "new formula"  # type: ignore[misc]

    d = exp.to_dict()
    assert d["formula"] == "debit = sum(C_i * IR_i * t_i)"
    assert d["constants_used"] == ["who_aqg_pm25_24h", "inhalation_rate_daily_mean"]
    assert len(d["sources"]) == 2


def test_constants_json_valid_and_complete() -> None:
    data_path = Path(__file__).resolve().parent.parent.parent / "data" / "constants.v1.json"
    doc = json.loads(data_path.read_text(encoding="utf-8"))
    assert doc["version"] == "v1"
    constants = doc["constants"]

    for _key, item in constants.items():
        assert "source" in item and len(item["source"]) > 5
        assert isinstance(item["verified"], bool)
        assert item["value"] is not None

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
        assert sources[required_src] > 0

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
        assert efs[required_ef]["kg_co2"] > 0
