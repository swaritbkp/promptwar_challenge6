"""Tests for hawakhata.engine.pets — pet walk risk and indoor guidance."""

from __future__ import annotations

import pytest

from hawakhata.engine.pets import (
    IndoorPetGuidance,
    PetWalkGuidance,
    evaluate_pet_walk_risk,
    get_indoor_pet_guidance,
)


@pytest.mark.parametrize(
    ("cat", "pm25", "exp_dur", "exp_pace", "exp_wipe"),
    [
        ("good", 10.0, 45, "normal", False),
        ("satisfactory", 35.0, 35, "normal", False),
        ("moderate", 65.0, 25, "gentle", True),
        ("poor", 120.0, 15, "gentle", True),
        ("very_poor", 200.0, 10, "relief_only", True),
        ("severe", 400.0, 5, "relief_only", True),
    ],
)
def test_pet_walk_bands(cat: str, pm25: float, exp_dur: int, exp_pace: str, exp_wipe: bool) -> None:
    res = evaluate_pet_walk_risk(pm25_ug_m3=pm25, aqi_category=cat)
    assert isinstance(res, PetWalkGuidance)
    assert (
        res.max_duration_min == exp_dur
        and res.pace == exp_pace
        and res.post_walk_wipe_needed == exp_wipe
    )


def test_all_bands_have_summary() -> None:
    for cat in ["good", "satisfactory", "moderate", "poor", "very_poor", "severe"]:
        r = evaluate_pet_walk_risk(pm25_ug_m3=100.0, aqi_category=cat)
        assert r.summary and len(r.instructions) >= 1


def test_edge_cases_and_clamp() -> None:
    assert evaluate_pet_walk_risk(pm25_ug_m3=0.0).max_duration_min > 0
    assert evaluate_pet_walk_risk(pm25_ug_m3=600.0).max_duration_min == 5
    assert evaluate_pet_walk_risk(pm25_ug_m3=-5.0, aqi_category="good").pm25_ug_m3 == 0.0
    assert (
        evaluate_pet_walk_risk(pm25_ug_m3=50.0, aqi_category="unknown_band").max_duration_min == 5
    )


def test_return_type_all_fields_present() -> None:
    r = evaluate_pet_walk_risk(pm25_ug_m3=120.0, aqi_category="severe")
    for f in [
        "aqi_category",
        "pm25_ug_m3",
        "max_duration_min",
        "pace",
        "post_walk_wipe_needed",
        "summary",
        "instructions",
    ]:
        assert hasattr(r, f)
    assert isinstance(r.instructions, list) and len(r.instructions) >= 2


@pytest.mark.parametrize(
    ("species", "vuln"),
    [("dog", "moderate"), ("cat", "high"), ("bird", "critical")],
)
def test_indoor_pet_guidance_species(species: str, vuln: str) -> None:
    r = get_indoor_pet_guidance(species)
    assert isinstance(r, IndoorPetGuidance)
    assert r.species == species and r.vulnerability_level == vuln
    assert len(r.warnings) >= 1 and len(r.practical_steps) >= 1
    assert hasattr(r, "airway_mechanisms")


def test_species_aliases_and_case() -> None:
    assert get_indoor_pet_guidance("DOG").species == "dog"
    assert get_indoor_pet_guidance("Cat").species == "cat"
    assert get_indoor_pet_guidance("BIRD").species == "bird"
    assert get_indoor_pet_guidance("avian").species == "bird"
    assert get_indoor_pet_guidance("parrot").species == "bird"
    assert get_indoor_pet_guidance("feline").species == "cat"
    assert get_indoor_pet_guidance("hamster").species == "dog"


def test_bird_special_warnings_and_levels() -> None:
    b = get_indoor_pet_guidance("bird")
    assert any("HEPA" in s for s in b.practical_steps)
    all_w = " ".join(b.warnings).lower()
    assert "incense" in all_w or "ptfe" in all_w or "aerosol" in all_w
    levels = {"critical": 3, "high": 2, "moderate": 1}
    assert (
        levels[b.vulnerability_level]
        > levels[get_indoor_pet_guidance("cat").vulnerability_level]
        > levels[get_indoor_pet_guidance("dog").vulnerability_level]
    )
