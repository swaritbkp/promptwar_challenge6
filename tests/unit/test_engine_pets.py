"""Tests for hawakhata.engine.pets — pet walk risk and indoor guidance."""

from __future__ import annotations

from hawakhata.engine.pets import (
    IndoorPetGuidance,
    PetWalkGuidance,
    evaluate_pet_walk_risk,
    get_indoor_pet_guidance,
)

# ---------------------------------------------------------------------------
# evaluate_pet_walk_risk — NAQI band coverage
# ---------------------------------------------------------------------------


def test_good_air_full_walk() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=10.0, aqi_category="good")
    assert isinstance(result, PetWalkGuidance)
    assert result.max_duration_min == 45
    assert result.pace == "normal"
    assert result.post_walk_wipe_needed is False
    assert result.aqi_category == "good"


def test_satisfactory_air_normal_walk() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=35.0, aqi_category="satisfactory")
    assert result.max_duration_min == 35
    assert result.pace == "normal"
    assert result.post_walk_wipe_needed is False


def test_moderate_air_gentle_walk() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=65.0, aqi_category="moderate")
    assert result.max_duration_min == 25
    assert result.pace == "gentle"
    assert result.post_walk_wipe_needed is True


def test_poor_air_gentle_short_walk() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=120.0, aqi_category="poor")
    assert result.max_duration_min == 15
    assert result.pace == "gentle"
    assert result.post_walk_wipe_needed is True


def test_very_poor_air_relief_only() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=200.0, aqi_category="very_poor")
    assert result.max_duration_min == 10
    assert result.pace == "relief_only"
    assert result.post_walk_wipe_needed is True


def test_severe_air_strict_relief() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=400.0, aqi_category="severe")
    assert result.max_duration_min == 5
    assert result.pace == "relief_only"
    assert result.post_walk_wipe_needed is True
    assert len(result.instructions) >= 2


def test_all_bands_have_summary() -> None:
    for cat in ["good", "satisfactory", "moderate", "poor", "very_poor", "severe"]:
        result = evaluate_pet_walk_risk(pm25_ug_m3=100.0, aqi_category=cat)
        assert result.summary, f"No summary for {cat}"
        assert len(result.instructions) >= 1


def test_pm25_zero_uses_category_fallback() -> None:
    """PM2.5=0 falls into 'good' auto-detected category."""
    result = evaluate_pet_walk_risk(pm25_ug_m3=0.0)
    assert isinstance(result, PetWalkGuidance)
    assert result.pm25_ug_m3 == 0.0
    assert result.max_duration_min > 0


def test_very_high_pm25_auto_category() -> None:
    """PM2.5=600 µg/m³ should auto-detect as 'severe'."""
    result = evaluate_pet_walk_risk(pm25_ug_m3=600.0)
    assert result.aqi_category == "severe"
    assert result.max_duration_min == 5


def test_negative_pm25_clamped_to_zero() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=-5.0, aqi_category="good")
    assert result.pm25_ug_m3 == 0.0


def test_return_type_all_fields_present() -> None:
    result = evaluate_pet_walk_risk(pm25_ug_m3=120.0, aqi_category="severe")
    assert hasattr(result, "aqi_category")
    assert hasattr(result, "pm25_ug_m3")
    assert hasattr(result, "max_duration_min")
    assert hasattr(result, "pace")
    assert hasattr(result, "post_walk_wipe_needed")
    assert hasattr(result, "summary")
    assert hasattr(result, "instructions")
    assert isinstance(result.instructions, list)


def test_unknown_category_falls_back_to_severe() -> None:
    """Unknown NAQI codes should default to severe (safest)."""
    result = evaluate_pet_walk_risk(pm25_ug_m3=50.0, aqi_category="unknown_band")
    assert result.max_duration_min == 5  # severe default


# ---------------------------------------------------------------------------
# get_indoor_pet_guidance — species coverage
# ---------------------------------------------------------------------------


def test_dog_guidance_moderate_vulnerability() -> None:
    result = get_indoor_pet_guidance("dog")
    assert isinstance(result, IndoorPetGuidance)
    assert result.species == "dog"
    assert result.vulnerability_level == "moderate"
    assert len(result.warnings) >= 1
    assert len(result.practical_steps) >= 1


def test_cat_guidance_high_vulnerability() -> None:
    result = get_indoor_pet_guidance("cat")
    assert result.species == "cat"
    assert result.vulnerability_level == "high"
    assert result.airway_mechanisms  # non-empty string


def test_bird_guidance_critical_vulnerability() -> None:
    result = get_indoor_pet_guidance("bird")
    assert result.species == "bird"
    assert result.vulnerability_level == "critical"
    assert any("HEPA" in s for s in result.practical_steps)


def test_species_case_insensitive() -> None:
    assert get_indoor_pet_guidance("DOG").species == "dog"
    assert get_indoor_pet_guidance("Cat").species == "cat"
    assert get_indoor_pet_guidance("BIRD").species == "bird"


def test_species_aliases_avian() -> None:
    assert get_indoor_pet_guidance("avian").species == "bird"
    assert get_indoor_pet_guidance("parrot").species == "bird"


def test_species_aliases_feline() -> None:
    assert get_indoor_pet_guidance("feline").species == "cat"


def test_unknown_species_defaults_to_dog() -> None:
    result = get_indoor_pet_guidance("hamster")
    assert result.species == "dog"


def test_indoor_guidance_all_fields_present() -> None:
    for sp in ["dog", "cat", "bird"]:
        result = get_indoor_pet_guidance(sp)
        assert hasattr(result, "species")
        assert hasattr(result, "vulnerability_level")
        assert hasattr(result, "airway_mechanisms")
        assert hasattr(result, "warnings")
        assert hasattr(result, "practical_steps")
        assert isinstance(result.warnings, list)
        assert isinstance(result.practical_steps, list)


def test_indoor_guidance_warnings_non_empty() -> None:
    for sp in ["dog", "cat", "bird"]:
        result = get_indoor_pet_guidance(sp)
        assert len(result.warnings) > 0, f"No warnings for {sp}"
        assert len(result.practical_steps) > 0, f"No steps for {sp}"


def test_bird_no_incense_warning() -> None:
    result = get_indoor_pet_guidance("bird")
    all_warnings = " ".join(result.warnings)
    assert "incense" in all_warnings.lower() or "PTFE" in all_warnings or "aerosol" in all_warnings


def test_vulnerability_levels_ordered() -> None:
    levels = {"critical": 3, "high": 2, "moderate": 1}
    bird = levels[get_indoor_pet_guidance("bird").vulnerability_level]
    cat = levels[get_indoor_pet_guidance("cat").vulnerability_level]
    dog = levels[get_indoor_pet_guidance("dog").vulnerability_level]
    assert bird > cat > dog
