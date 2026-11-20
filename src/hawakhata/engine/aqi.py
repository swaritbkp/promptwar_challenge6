"""India National Air Quality Index (NAQI) categorization and PM2.5 sub-index math."""

from __future__ import annotations

from dataclasses import dataclass


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

_PM25_BREAKPOINTS: tuple[tuple[float, float, int, int, str], ...] = (
    (0.0, 30.0, 0, 50, "good"),
    (30.0, 60.0, 50, 100, "satisfactory"),
    (60.0, 90.0, 100, 200, "moderate"),
    (90.0, 120.0, 200, 300, "poor"),
    (120.0, 250.0, 300, 400, "very_poor"),
    (250.0, 500.0, 400, 500, "severe"),
)


def pm25_to_naqi_category(pm25_ug_m3: float) -> NAQICategory:
    """Map a PM2.5 concentration in ug/m3 to the corresponding CPCB NAQI category."""
    c = max(0.0, pm25_ug_m3)
    if c <= 30.0:
        return CATEGORIES["good"]
    if c <= 60.0:
        return CATEGORIES["satisfactory"]
    if c <= 90.0:
        return CATEGORIES["moderate"]
    if c <= 120.0:
        return CATEGORIES["poor"]
    if c <= 250.0:
        return CATEGORIES["very_poor"]
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
    for b_low, b_high, i_low, i_high, _ in _PM25_BREAKPOINTS:
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
