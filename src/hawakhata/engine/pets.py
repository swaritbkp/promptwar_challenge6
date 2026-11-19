"""Deterministic pet air-quality guidance for outdoor walks and indoor housing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hawakhata.engine.aqi import pm25_to_naqi_category


@dataclass(frozen=True, slots=True)
class PetWalkGuidance:
    """Safe walk duration and care steps for household pets."""

    aqi_category: str
    pm25_ug_m3: float
    max_duration_min: int
    pace: Literal["normal", "gentle", "relief_only"]
    post_walk_wipe_needed: bool
    summary: str
    instructions: list[str]


@dataclass(frozen=True, slots=True)
class IndoorPetGuidance:
    """Species indoor air vulnerability profile and protective steps."""

    species: str
    vulnerability_level: Literal["critical", "high", "moderate"]
    airway_mechanisms: str
    warnings: list[str]
    practical_steps: list[str]


_WALK_RULES: dict[
    str, tuple[int, Literal["normal", "gentle", "relief_only"], bool, str, list[str]]
] = {
    "good": (
        45,
        "normal",
        False,
        "Air clean. Regular outdoor walks safe.",
        ["Maintain regular exercise."],
    ),
    "satisfactory": (
        35,
        "normal",
        False,
        "Air acceptable. Standard walks safe.",
        ["Standard walks fine."],
    ),
    "moderate": (
        25,
        "gentle",
        True,
        "Moderate soot. Walk 25m max.",
        ["Avoid busy traffic junctions.", "Wipe paws after return."],
    ),
    "poor": (
        15,
        "gentle",
        True,
        "Poor air. 15m gentle stroll only.",
        ["No strenuous outdoor running.", "Wipe paws and muzzle."],
    ),
    "very_poor": (
        10,
        "relief_only",
        True,
        "Very Poor air. 10m relief breaks.",
        ["Short 10m relief trips only.", "Damp wipe of paws and coat."],
    ),
    "severe": (
        5,
        "relief_only",
        True,
        "Severe smog. 5m bathroom trips only.",
        ["Strict 5m relief trips.", "Mandatory damp wipe on entry.", "Indoor mental games."],
    ),
}


def evaluate_pet_walk_risk(pm25_ug_m3: float, aqi_category: str | None = None) -> PetWalkGuidance:
    """Evaluate safe outdoor walk duration and post-walk grooming requirements."""
    cat = aqi_category or pm25_to_naqi_category(pm25_ug_m3).code
    val = max(0.0, pm25_ug_m3)
    dur, pace, wipe, summary, instrs = _WALK_RULES.get(cat, _WALK_RULES["severe"])
    return PetWalkGuidance(cat, val, dur, pace, wipe, summary, instrs)


_INDOOR_SPECIES: dict[
    str, tuple[Literal["critical", "high", "moderate"], str, list[str], list[str]]
] = {
    "bird": (
        "critical",
        "Avian air sacs absorb fine particulates and toxic gases rapidly.",
        ["Zero incense/dhoop/coils.", "PTFE/Teflon non-stick fumes fatal.", "No aerosol sprays."],
        [
            "Run HEPA continuously in bird room.",
            "Keep cage away from kitchen exhaust.",
            "Clean cage daily.",
        ],
    ),
    "cat": (
        "high",
        "Feline airways are highly vulnerable to particulate asthma.",
        [
            "Avoid dusty clay or silica litters.",
            "Do not scoop litter in closed rooms.",
            "Avoid aerosol sprays.",
        ],
        [
            "Switch to low-dust pellet or paper litter.",
            "Direct HEPA airflow near perches.",
            "Brush fur regularly.",
        ],
    ),
    "dog": (
        "moderate",
        "PM2.5 reaches deep lung tissue. Brachycephalic breeds face higher distress.",
        ["No smoke or incense in sleeping areas.", "Avoid indoor ball games in unpurified rooms."],
        [
            "Indoor snuffle mats for exercise.",
            "Wipe paws with damp cloth after relief trips.",
            "Run bedroom HEPA overnight.",
        ],
    ),
}


def get_indoor_pet_guidance(species: str) -> IndoorPetGuidance:
    """Return verified veterinary indoor air guidance for dogs, cats, and birds."""
    sp = species.lower().strip()
    key = (
        "bird"
        if ("bird" in sp or "avian" in sp or "parrot" in sp)
        else ("cat" if ("cat" in sp or "feline" in sp) else "dog")
    )
    vuln, mech, warns, steps = _INDOOR_SPECIES[key]
    return IndoorPetGuidance(key, vuln, mech, warns, steps)
