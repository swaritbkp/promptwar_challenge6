"""India National Air Quality Index (NAQI) categorization and PM2.5 sub-index math."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from hawakhata.engine.constants import get_constant


@dataclass(frozen=True, slots=True)
class NAQICategory:
    """Represents a discrete NAQI air quality category band."""

    code: str
    display_name: str
    label_key: str
    icon_key: str
    color_hex: str


CATEGORIES: dict[str, NAQICategory] = {
    "good": NAQICategory("good", "Good", "naqi.category.good", "smile", "#2E7D32"),
    "satisfactory": NAQICategory(
        "satisfactory", "Satisfactory", "naqi.category.satisfactory", "leaf", "#7CB342"
    ),
    "moderate": NAQICategory("moderate", "Moderate", "naqi.category.moderate", "cloud", "#C9A400"),
    "poor": NAQICategory("poor", "Poor", "naqi.category.poor", "haze", "#E07B00"),
    "very_poor": NAQICategory(
        "very_poor", "Very Poor", "naqi.category.very_poor", "mask", "#C62828"
    ),
    "severe": NAQICategory(
        "severe", "Severe", "naqi.category.severe", "warning_triangle", "#6A1B4D"
    ),
}

_SUB_INDEX_EDGES: tuple[int, ...] = (0, 50, 100, 200, 300, 400, 500)
_SEVERE_INTERP_CEILING_UG_M3 = 500.0  # PM2.5 at which the sub-index reaches 500 (linear above)


@lru_cache(maxsize=1)
def _pm25_breakpoints() -> tuple[tuple[float, float, int, int, str], ...]:
    """Build (c_low, c_high, i_low, i_high, code) bands from data/constants.v1.json.

    constants.v1.json lists CPCB integer bands ([0,30], [31,60], ...). Real readings are
    continuous, so each band runs from the previous band's upper edge (exclusive) to its
    own upper edge (inclusive): 30.0 -> Good, 30.4 -> Satisfactory. The integer lower
    bound (31) and the continuous edge (30) therefore describe the same CPCB boundary.
    """
    rows = get_constant("naqi_pm25_breakpoints").value
    bands: list[tuple[float, float, int, int, str]] = []
    prev_upper = 0.0
    for idx, (_low, high, code) in enumerate(rows):
        upper = _SEVERE_INTERP_CEILING_UG_M3 if code == "severe" else float(high)
        bands.append((prev_upper, upper, _SUB_INDEX_EDGES[idx], _SUB_INDEX_EDGES[idx + 1], code))
        prev_upper = upper
    return tuple(bands)


def pm25_to_naqi_category(pm25_ug_m3: float) -> NAQICategory:
    """Map a PM2.5 concentration in ug/m3 to the CPCB NAQI category.

    Band edges come from ``naqi_pm25_breakpoints`` in data/constants.v1.json
    (Good <=30, Satisfactory <=60, Moderate <=90, Poor <=120, Very Poor <=250, Severe >250).
    The upper band-edge belongs to the LOWER severity band (exactly 30 -> Good).
    """
    c = max(0.0, pm25_ug_m3)
    for _low, high, _il, _ih, code in _pm25_breakpoints()[:-1]:
        if c <= high:
            return CATEGORIES[code]
    return CATEGORIES["severe"]


def aqi_to_category(aqi: int | float) -> NAQICategory:
    """Map an integer or float AQI value directly to its NAQI category band."""
    val = max(0.0, float(aqi))
    if val <= 50.0:
        return CATEGORIES["good"]
    if val <= 100.0:
        return CATEGORIES["satisfactory"]
    if val <= 200.0:
        return CATEGORIES["moderate"]
    if val <= 300.0:
        return CATEGORIES["poor"]
    if val <= 400.0:
        return CATEGORIES["very_poor"]
    return CATEGORIES["severe"]


def pm25_to_sub_index(pm25_ug_m3: float) -> int:
    """Compute numerical CPCB sub-index for PM2.5 using piecewise linear interpolation."""
    c = max(0.0, pm25_ug_m3)
    for b_low, b_high, i_low, i_high, _ in _pm25_breakpoints():
        if b_low <= c <= b_high:
            sub = i_low + (i_high - i_low) / (b_high - b_low) * (c - b_low)
            return round(sub)
    return round(500 + (c - 500.0) * (100.0 / 250.0))


def compute_live_aq_snapshot(pm25_ug_m3: float) -> tuple[float, int, str, str]:
    """Compute verified live PM2.5, NAQI sub-index, category code, and display label.

    Returns:
        (current_pm25, current_aqi, current_category_code, current_category_display_name)
    """
    pm = round(max(0.0, float(pm25_ug_m3)), 1)
    aqi = pm25_to_sub_index(pm)
    cat = pm25_to_naqi_category(pm)
    return pm, aqi, cat.code, cat.display_name


@dataclass(frozen=True, slots=True)
class GrapStage:
    """Graded Response Action Plan stage derived deterministically from CPCB NAQI."""

    stage: int
    code: str
    label_en: str
    label_hi: str
    aqi: int
    advisories_en: list[str]
    advisories_hi: list[str]
    scope_note_en: str
    scope_note_hi: str


@lru_cache(maxsize=1)
def _grap_text() -> dict[str, object]:
    path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "grap.v1.json"
    return dict(json.loads(path.read_text("utf-8")))


def aqi_to_grap_stage(aqi: int | float) -> GrapStage:
    """Map NAQI to GRAP stage using ``grap_stage_aqi_thresholds`` (<=200 Normal, I-IV above).

    Thresholds are CAQM's Delhi-NCR triggers; elsewhere the stage is shown as the
    equivalent national CPCB severity level, which the scope note states explicitly.
    """
    val = round(max(0.0, float(aqi)))
    stage, code = 0, "normal"
    for idx, (low, _high, roman) in enumerate(get_constant("grap_stage_aqi_thresholds").value):
        if val >= int(low):
            stage, code = idx + 1, str(roman)
    text = _grap_text()
    stages = text["stages"]
    entry = stages[code] if isinstance(stages, dict) else {}
    return GrapStage(
        stage=stage,
        code=code,
        label_en=str(entry["label_en"]),
        label_hi=str(entry["label_hi"]),
        aqi=val,
        advisories_en=list(entry["advisories_en"]),
        advisories_hi=list(entry["advisories_hi"]),
        scope_note_en=str(text["scope_note_en"]),
        scope_note_hi=str(text["scope_note_hi"]),
    )
