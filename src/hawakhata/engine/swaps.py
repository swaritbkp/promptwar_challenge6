"""Sustainable alternatives (swaps) and Mohalla (community) scaling engine.

Calculates:
    - Delta emit: avoided CO2 (kg) and PM2.5 (g) across daily, weekly, and monthly horizons.
    - Delta breathe: personal particulate inhalation dose avoided per member.
    - Community multiplier: linear aggregate impact scaled by household count and adoption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hawakhata.engine.constants import get_constant
from hawakhata.engine.emissions import activity_emissions
from hawakhata.engine.explain import Explanation

MONTHS_IN_WEEKS_MULTIPLIER = 4.33
DEFAULT_DAYS_PER_WEEK = 5
MIN_DAYS_PER_WEEK = 1
MAX_DAYS_PER_WEEK = 7
DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data"


@dataclass(frozen=True, slots=True)
class DeltaEmission:
    """Emission change from a sustainable swap (negative values indicate reductions).

    Attributes:
        kg_co2: Net greenhouse gas difference in kilograms of CO2 equivalent.
        g_pm25: Net direct particulate difference in grams of PM2.5.
    """

    kg_co2: float
    g_pm25: float


@dataclass(frozen=True, slots=True)
class SwapImpactResult:
    """Multi-horizon emissions and exposure impact of an adopted lifestyle swap.

    Attributes:
        swap_id: Unique swap identifier from the catalogue.
        title: Descriptive human-readable swap title.
        delta_emit_daily: Emission delta per single active day.
        delta_emit_weekly: Emission delta across the weekly active days.
        delta_emit_monthly: Emission delta across an average month (4.33 weeks).
        delta_breathe_daily_ug: Personal daily dose change in micrograms (negative = avoided dose).
        explanation: Provenance, formulas, and scientific citations.
    """

    swap_id: str
    title: str
    delta_emit_daily: DeltaEmission
    delta_emit_weekly: DeltaEmission
    delta_emit_monthly: DeltaEmission
    delta_breathe_daily_ug: float
    explanation: Explanation


@dataclass(frozen=True, slots=True)
class CommunityImpactResult:
    """Scaled collective impact across a residential colony, sector, or mohalla.

    Attributes:
        households: Number of candidate households in the community.
        participation_rate: Fractional adoption rate between 0.0 and 1.0.
        community_delta_co2_kg_monthly: Avoided community CO2 emissions per month (kg).
        community_delta_pm25_g_monthly: Avoided community PM2.5 emissions per month (g).
        community_avoided_dose_monthly_mg: Cumulative personal inhaled particulate avoided (mg).
        explanation: Scaling formulas and assumptions.
    """

    households: int
    participation_rate: float
    community_delta_co2_kg_monthly: float
    community_delta_pm25_g_monthly: float
    community_avoided_dose_monthly_mg: float
    explanation: Explanation


def get_available_swaps() -> list[dict[str, Any]]:
    """Return the list of curated sustainable alternatives from constants.v1.json.

    Returns:
        List of swap definitions with id, before, after, and affected domains.
    """
    constants_file = DATA_ROOT / "constants.v1.json"
    with constants_file.open(encoding="utf-8") as f:
        data = json.load(f)
    catalogue = data.get("swap_catalogue", [])
    if isinstance(catalogue, list):
        return [dict(item) for item in catalogue if isinstance(item, dict)]
    return []


def _safe_activity_emissions(act: str | None, units: float) -> tuple[float, float]:
    """Calculate central CO2 (kg) and PM2.5 (g) for an activity, returning 0 on missing."""
    if not act:
        return 0.0, 0.0
    try:
        res = activity_emissions(act, units)
        return res.kg_co2.central, res.g_pm25.central
    except KeyError:
        return 0.0, 0.0


def _compute_transit_delta_breathe(
    before_act: str | None,
    after_act: str | None,
    outdoor_pm25_mean: float,
    member_age_band: str,
    duration_hours: float,
) -> float:
    """Calculate personal inhaled dose difference in ug during transit."""
    vehicle_ratios = get_constant("in_vehicle_ratio").value
    r_before = 0.65  # default car
    r_after = 0.50  # default metro
    if isinstance(vehicle_ratios, dict):
        if before_act and "two_wheeler" in before_act:
            r_before = float(vehicle_ratios.get("transit_two_wheeler", 1.3))
        elif before_act and "car" in before_act:
            r_before = float(vehicle_ratios.get("transit_car", 0.65))

        if after_act and "metro" in after_act:
            r_after = float(vehicle_ratios.get("transit_metro", 0.5))
        elif after_act and "bus" in after_act:
            r_after = float(vehicle_ratios.get("transit_public", 1.0))

    ir_mean_const = get_constant("inhalation_rate_daily_mean").value
    ir_mult_const = get_constant("activity_multiplier").value
    daily_mean = 16.0
    if isinstance(ir_mean_const, dict):
        daily_mean = float(ir_mean_const.get(member_age_band, 16.0))
    mult = 1.0
    if isinstance(ir_mult_const, dict):
        mult = float(ir_mult_const.get("light", 1.0))

    ir_hourly = (daily_mean / 24.0) * mult
    c_before = outdoor_pm25_mean * r_before
    c_after = outdoor_pm25_mean * r_after
    return round((c_after - c_before) * ir_hourly * duration_hours, 2)


def evaluate_swap(
    swap_id: str,
    units_per_day: float,
    *,
    days_per_week: int = DEFAULT_DAYS_PER_WEEK,
    outdoor_pm25_mean: float = 150.0,
    member_age_band: str = "31_41",
    transit_duration_hours: float = 1.0,
) -> SwapImpactResult:
    """Evaluate emission and exposure deltas for an adopted sustainable lifestyle swap.

    Formulas:
        Delta_emit(day) = Emission(after) - Emission(before)
        Delta_emit(week) = Delta_emit(day) * days_per_week
        Delta_emit(month) = Delta_emit(week) * 4.33
        Delta_breathe(day) = (Ratio_after - Ratio_before) * C_out * IR_h * hours

    Args:
        swap_id: Catalogue identifier for the swap.
        units_per_day: Activity units replaced per day (e.g. km commuted, hours heated).
        days_per_week: Number of active days per week (1..7).
        outdoor_pm25_mean: Ambient PM2.5 concentration during activity (ug/m3).
        member_age_band: Age band for inhalation rate calculation.
        transit_duration_hours: Exposure duration during the activity (hours).

    Returns:
        SwapImpactResult detailing daily, weekly, and monthly deltas.

    Raises:
        KeyError: If swap_id is not in the catalogue.
        ValueError: If units_per_day or days_per_week is invalid.
    """
    if units_per_day < 0:
        raise ValueError(f"units_per_day must be non-negative, got {units_per_day}")
    if not (MIN_DAYS_PER_WEEK <= days_per_week <= MAX_DAYS_PER_WEEK):
        raise ValueError(f"days_per_week must be between 1 and 7, got {days_per_week}")

    catalogue = get_available_swaps()
    swap_def = next((s for s in catalogue if s.get("id") == swap_id), None)
    if swap_def is None:
        raise KeyError(f"Unknown swap_id '{swap_id}' in catalogue")

    before_act = swap_def.get("before")
    after_act = swap_def.get("after")

    before_co2, before_pm = _safe_activity_emissions(before_act, units_per_day)
    after_co2, after_pm = _safe_activity_emissions(after_act, units_per_day)

    # Delta emissions (negative indicates reduction)
    d_co2_daily = round(after_co2 - before_co2, 4)
    d_pm_daily = round(after_pm - before_pm, 4)

    d_co2_weekly = round(d_co2_daily * days_per_week, 4)
    d_pm_weekly = round(d_pm_daily * days_per_week, 4)

    d_co2_monthly = round(d_co2_weekly * MONTHS_IN_WEEKS_MULTIPLIER, 4)
    d_pm_monthly = round(d_pm_weekly * MONTHS_IN_WEEKS_MULTIPLIER, 4)

    delta_breathe_daily = 0.0
    affects = swap_def.get("affects", [])
    if "breathe_transit" in affects:
        delta_breathe_daily = _compute_transit_delta_breathe(
            before_act=before_act,
            after_act=after_act,
            outdoor_pm25_mean=outdoor_pm25_mean,
            member_age_band=member_age_band,
            duration_hours=transit_duration_hours,
        )

    title = swap_id.replace("_", " ").title()

    exp = Explanation(
        formula="Delta_emit = Emission(after) - Emission(before); "
        "Delta_breathe = (C_after - C_before) * IR * duration",
        inputs={
            "swap_id": swap_id,
            "units_per_day": f"{units_per_day:.2f}",
            "days_per_week": str(days_per_week),
            "delta_co2_monthly": f"{d_co2_monthly:.2f} kg",
            "delta_pm25_monthly": f"{d_pm_monthly:.2f} g",
            "delta_breathe_daily": f"{delta_breathe_daily:.1f} ug",
        },
        constants_used=["emission_factor", "in_vehicle_ratio", "inhalation_rate_daily_mean"],
        sources=[
            "ARAI (2018) Indian vehicular emission factors",
            "Goel & Kumar (2015) Atmospheric Environment commuter exposure",
        ],
        assumptions=[
            "Linear scaling across weekly and monthly active horizons (4.33 weeks/month)",
            "Constant emission factors and travel speed across trip segments",
        ],
    )

    return SwapImpactResult(
        swap_id=swap_id,
        title=title,
        delta_emit_daily=DeltaEmission(kg_co2=d_co2_daily, g_pm25=d_pm_daily),
        delta_emit_weekly=DeltaEmission(kg_co2=d_co2_weekly, g_pm25=d_pm_weekly),
        delta_emit_monthly=DeltaEmission(kg_co2=d_co2_monthly, g_pm25=d_pm_monthly),
        delta_breathe_daily_ug=delta_breathe_daily,
        explanation=exp,
    )


def scale_to_community(
    swap_result: SwapImpactResult,
    households: int,
    participation_rate: float,
) -> CommunityImpactResult:
    """Scale a household swap delta to community (Mohalla) level.

    Formula:
        Community_Delta = Per_Household_Delta * Households * ParticipationRate

    Invariants:
        - Strictly linear in households and participation_rate.
        - Exactly 0.0 when participation_rate == 0.0 or households == 0.

    Args:
        swap_result: Single household swap impact outcome.
        households: Number of participating residential units.
        participation_rate: Adoption percentage (0.0 to 1.0).

    Returns:
        CommunityImpactResult with scaled monthly emissions and avoided dose.

    Raises:
        ValueError: If households < 0 or participation_rate not in [0.0, 1.0].
    """
    if households < 0:
        raise ValueError(f"households must be non-negative, got {households}")
    if not (0.0 <= participation_rate <= 1.0):
        msg = f"participation_rate must be between 0.0 and 1.0, got {participation_rate}"
        raise ValueError(msg)

    effective_units = float(households) * participation_rate

    co2_monthly = round(swap_result.delta_emit_monthly.kg_co2 * effective_units, 2)
    pm25_monthly = round(swap_result.delta_emit_monthly.g_pm25 * effective_units, 2)

    # Inhaled particulate avoided across community per month (ug converted to mg: / 1000)
    # Monthly exposure avoided = daily avoided * 30 days
    daily_avoided_ug = max(0.0, -swap_result.delta_breathe_daily_ug)
    monthly_dose_mg = round((daily_avoided_ug * 30.0 * effective_units) / 1000.0, 2)

    exp = Explanation(
        formula="Community_Impact = Per_Household_Impact * Households * ParticipationRate",
        inputs={
            "households": str(households),
            "participation_rate": f"{participation_rate:.2%}",
            "effective_participating_households": f"{effective_units:.1f}",
            "community_co2_monthly": f"{co2_monthly:.2f} kg",
            "community_pm25_monthly": f"{pm25_monthly:.2f} g",
        },
        constants_used=["emission_factor"],
        sources=["Mohalla linear aggregation model"],
        assumptions=[
            "Adoption is independent across participating households",
            "Homogeneous baseline activity levels across candidate units",
        ],
    )

    return CommunityImpactResult(
        households=households,
        participation_rate=participation_rate,
        community_delta_co2_kg_monthly=co2_monthly,
        community_delta_pm25_g_monthly=pm25_monthly,
        community_avoided_dose_monthly_mg=monthly_dose_mg,
        explanation=exp,
    )
