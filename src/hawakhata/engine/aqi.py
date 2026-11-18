"""India National Air Quality Index (NAQI) categorization and PM2.5 sub-index math.

Based on CPCB NAQI guidelines (2014) and visual tokens from DESIGN.md.
Color is NEVER the sole signal: every category provides text label keys and
accessible icon tokens.
"""

from __future__ import annotations

from dataclasses import dataclass

# PM2.5 24-h concentration upper thresholds (ug/m3) per CPCB
PM25_GOOD_MAX = 30.0
PM25_SATISFACTORY_MAX = 60.0
PM25_MODERATE_MAX = 90.0
PM25_POOR_MAX = 120.0
PM25_VERY_POOR_MAX = 250.0
PM25_EXTRAPOLATION_BASE = 500.0

# AQI value upper thresholds
AQI_GOOD_MAX = 50.0
AQI_SATISFACTORY_MAX = 100.0
AQI_MODERATE_MAX = 200.0
AQI_POOR_MAX = 300.0
AQI_VERY_POOR_MAX = 400.0


@dataclass(frozen=True, slots=True)
class NAQICategory:
    """Represents a discrete NAQI air quality category band.

    Attributes:
        code: Machine key ('good', 'satisfactory', 'moderate', 'poor', 'very_poor', 'severe').
        display_name: Human readable title in English.
        label_key: i18n translation key in static/i18n/{en,hi}.json.
        icon_key: SVG sprite identifier ('smile', 'leaf', 'cloud', 'haze', 'mask',
            'warning_triangle').
        color_hex: Hex code token from DESIGN.md.
    """

    code: str
    display_name: str
    label_key: str
    icon_key: str
    color_hex: str


CATEGORIES: dict[str, NAQICategory] = {
    "good": NAQICategory(
        code="good",
        display_name="Good",
        label_key="naqi.category.good",
        icon_key="smile",
        color_hex="#2E7D32",
    ),
    "satisfactory": NAQICategory(
        code="satisfactory",
        display_name="Satisfactory",
        label_key="naqi.category.satisfactory",
        icon_key="leaf",
        color_hex="#7CB342",
    ),
    "moderate": NAQICategory(
        code="moderate",
        display_name="Moderate",
        label_key="naqi.category.moderate",
        icon_key="cloud",
        color_hex="#C9A400",
    ),
    "poor": NAQICategory(
        code="poor",
        display_name="Poor",
        label_key="naqi.category.poor",
        icon_key="haze",
        color_hex="#E07B00",
    ),
    "very_poor": NAQICategory(
        code="very_poor",
        display_name="Very Poor",
        label_key="naqi.category.very_poor",
        icon_key="mask",
        color_hex="#C62828",
    ),
    "severe": NAQICategory(
        code="severe",
        display_name="Severe",
        label_key="naqi.category.severe",
        icon_key="warning_triangle",
        color_hex="#6A1B4D",
    ),
}

# CPCB PM2.5 Breakpoints: (low_concentration, high_concentration, low_aqi, high_aqi, category_code)
_PM25_BREAKPOINTS: tuple[tuple[float, float, int, int, str], ...] = (
    (0.0, 30.0, 0, 50, "good"),
    (30.0, 60.0, 50, 100, "satisfactory"),
    (60.0, 90.0, 100, 200, "moderate"),
    (90.0, 120.0, 200, 300, "poor"),
    (120.0, 250.0, 300, 400, "very_poor"),
    (250.0, 500.0, 400, 500, "severe"),
)


def pm25_to_naqi_category(pm25_ug_m3: float) -> NAQICategory:
    """Map a PM2.5 concentration in ug/m3 to the corresponding CPCB NAQI category.

    Args:
        pm25_ug_m3: Inhaled or outdoor PM2.5 concentration in ug/m3. Negative values
            are clamped to 0.

    Returns:
        NAQICategory instance containing code, display name, label_key, icon_key, and color.
    """
    c = max(0.0, pm25_ug_m3)
    if c <= PM25_GOOD_MAX:
        return CATEGORIES["good"]
    if c <= PM25_SATISFACTORY_MAX:
        return CATEGORIES["satisfactory"]
    if c <= PM25_MODERATE_MAX:
        return CATEGORIES["moderate"]
    if c <= PM25_POOR_MAX:
        return CATEGORIES["poor"]
    if c <= PM25_VERY_POOR_MAX:
        return CATEGORIES["very_poor"]
    return CATEGORIES["severe"]


def aqi_to_category(aqi: int | float) -> NAQICategory:
    """Map an integer or float AQI value directly to its NAQI category band.

    Args:
        aqi: Numerical AQI value (0 to 500+). Negative values are clamped to 0.

    Returns:
        NAQICategory instance.
    """
    val = max(0.0, float(aqi))
    if val <= AQI_GOOD_MAX:
        return CATEGORIES["good"]
    if val <= AQI_SATISFACTORY_MAX:
        return CATEGORIES["satisfactory"]
    if val <= AQI_MODERATE_MAX:
        return CATEGORIES["moderate"]
    if val <= AQI_POOR_MAX:
        return CATEGORIES["poor"]
    if val <= AQI_VERY_POOR_MAX:
        return CATEGORIES["very_poor"]
    return CATEGORIES["severe"]


def pm25_to_sub_index(pm25_ug_m3: float) -> int:
    """Compute the numerical CPCB sub-index for PM2.5 using piecewise linear interpolation.

    Formula:
        I = I_low + (I_high - I_low) / (B_high - B_low) * (C - B_low)

    Args:
        pm25_ug_m3: Concentration in ug/m3.

    Returns:
        Integer AQI sub-index (0 to 500+).
    """
    c = max(0.0, pm25_ug_m3)
    for b_low, b_high, i_low, i_high, _ in _PM25_BREAKPOINTS:
        if b_low <= c <= b_high:
            sub = i_low + (i_high - i_low) / (b_high - b_low) * (c - b_low)
            return round(sub)

    # Beyond 500 ug/m3, extrapolate using the severe slope (100 AQI per 250 ug/m3)
    extra_c = c - PM25_EXTRAPOLATION_BASE
    return round(500 + extra_c * (100.0 / 250.0))
