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
    assert c.value == 15 and c.unit == "ug_m3" and c.source != "" and c.verified is True


def test_get_constant_success_and_missing() -> None:
    c = get_constant("who_aqg_pm25_24h")
    assert c.id == "who_aqg_pm25_24h" and c.value == 15
    with pytest.raises(KeyError, match="Unknown constant id"):
        get_constant("non_existent_constant_id_123")


def test_load_constants_errors(tmp_path: Path) -> None:
    with pytest.raises(ValidationFailedError, match="not found"):
        load_constants(Path("/non/existent/path/constants.json"))
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("not json", encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="Failed to parse"):
        load_constants(bad_json)
    empty_obj = tmp_path / "empty.json"
    empty_obj.write_text('{"foo": "bar"}', encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="root 'constants' mapping"):
        load_constants(empty_obj)
    bad_entry = tmp_path / "bad_entry.json"
    bad_entry.write_text('{"constants": {"k": "not a dict"}}', encoding="utf-8")
    with pytest.raises(ValidationFailedError, match="invalid schema"):
        load_constants(bad_entry)


def test_explanation_frozen_and_serializable() -> None:
    exp = Explanation(
        "debit = sum(C_i * IR_i * t_i)",
        {"C_avg": "150 ug/m3"},
        ["who_aqg_pm25_24h"],
        ["WHO 2021"],
        ["Assump"],
    )
    with pytest.raises(AttributeError):
        exp.formula = "new formula"  # type: ignore[misc]
    assert exp.to_dict()["formula"] == "debit = sum(C_i * IR_i * t_i)"


def test_constants_json_valid_and_complete() -> None:
    p = Path(__file__).resolve().parent.parent.parent / "data" / "constants.v1.json"
    doc = json.loads(p.read_text("utf-8"))
    assert doc["version"] == "v1"
    constants = doc["constants"]
    for item in constants.values():
        assert (
            "source" in item
            and len(item["source"]) > 5
            and isinstance(item["verified"], bool)
            and item["value"] is not None
        )

    sources = constants["indoor_source_emission_rate"]["value"]
    assert all(
        sources[s] > 0
        for s in [
            "src_frying",
            "src_tadka",
            "src_incense_stick",
            "src_mosquito_coil",
            "src_candle",
            "src_angithi_coal",
        ]
    )

    efs = constants["emission_factor"]["value"]
    assert all(
        efs[e]["kg_co2"] > 0
        for e in [
            "car_petrol_per_km",
            "two_wheeler_per_km",
            "metro_per_passenger_km",
            "open_leaf_burning_per_kg",
        ]
    )
