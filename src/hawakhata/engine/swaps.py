"""Sustainable alternatives (swaps) and Mohalla (community) scaling engine."""

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
    """Emissions delta from a sustainable swap (negative indicates reduction)."""

    kg_co2: float
    g_pm25: float


@dataclass(frozen=True, slots=True)
class SwapImpactResult:
    """Emissions and personal exposure reduction from an adopted lifestyle swap."""

    swap_id: str
    title: str
    delta_emit_daily: DeltaEmission
    delta_emit_weekly: DeltaEmission
    delta_emit_monthly: DeltaEmission
    delta_breathe_daily_ug: float
    explanation: Explanation


@dataclass(frozen=True, slots=True)
class CommunityImpactResult:
    """Scaled collective impact across a residential mohalla."""

    households: int
    participation_rate: float
    community_delta_co2_kg_monthly: float
    community_delta_pm25_g_monthly: float
    community_avoided_dose_monthly_mg: float
    explanation: Explanation


def get_available_swaps() -> list[dict[str, Any]]:
    """Return curated sustainable alternatives from constants.v1.json."""
    with (DATA_ROOT / "constants.v1.json").open(encoding="utf-8") as f:
        catalogue = json.load(f).get("swap_catalogue", [])
    return [dict(item) for item in catalogue if isinstance(item, dict)]


def _safe_activity_emissions(act: str | None, units: float) -> tuple[float, float]:
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
    vehicle_ratios = get_constant("in_vehicle_ratio").value
    r_before, r_after = 0.65, 0.50
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
    daily_mean = (
        float(ir_mean_const.get(member_age_band, 16.0)) if isinstance(ir_mean_const, dict) else 16.0
    )
    ir_hourly = daily_mean / 24.0
    return round(
        ((outdoor_pm25_mean * r_after) - (outdoor_pm25_mean * r_before))
        * ir_hourly
        * duration_hours,
        2,
    )


def evaluate_swap(
    swap_id: str,
    units_per_day: float,
    *,
    days_per_week: int = DEFAULT_DAYS_PER_WEEK,
    outdoor_pm25_mean: float = 150.0,
    member_age_band: str = "31_41",
    transit_duration_hours: float = 1.0,
) -> SwapImpactResult:
    """Evaluate emission and exposure deltas for an adopted sustainable lifestyle swap."""
    if units_per_day < 0:
        raise ValueError(f"units_per_day must be non-negative, got {units_per_day}")
    if not (MIN_DAYS_PER_WEEK <= days_per_week <= MAX_DAYS_PER_WEEK):
        raise ValueError(f"days_per_week must be between 1 and 7, got {days_per_week}")

    catalogue = get_available_swaps()
    swap_def = next((s for s in catalogue if s.get("id") == swap_id), None)
    if swap_def is None:
        raise KeyError(f"Unknown swap_id '{swap_id}' in catalogue")

    before_co2, before_pm = _safe_activity_emissions(swap_def.get("before"), units_per_day)
    after_co2, after_pm = _safe_activity_emissions(swap_def.get("after"), units_per_day)

    d_co2_daily, d_pm_daily = round(after_co2 - before_co2, 4), round(after_pm - before_pm, 4)
    d_co2_weekly, d_pm_weekly = (
        round(d_co2_daily * days_per_week, 4),
        round(d_pm_daily * days_per_week, 4),
    )
    d_co2_monthly = round(d_co2_weekly * MONTHS_IN_WEEKS_MULTIPLIER, 4)
    d_pm_monthly = round(d_pm_weekly * MONTHS_IN_WEEKS_MULTIPLIER, 4)
    delta_breathe_daily = (
        _compute_transit_delta_breathe(
            swap_def.get("before"),
            swap_def.get("after"),
            outdoor_pm25_mean,
            member_age_band,
            transit_duration_hours,
        )
        if "breathe_transit" in swap_def.get("affects", [])
        else 0.0
    )

    return SwapImpactResult(
        swap_id=swap_id,
        title=swap_id.replace("_", " ").title(),
        delta_emit_daily=DeltaEmission(kg_co2=d_co2_daily, g_pm25=d_pm_daily),
        delta_emit_weekly=DeltaEmission(kg_co2=d_co2_weekly, g_pm25=d_pm_weekly),
        delta_emit_monthly=DeltaEmission(kg_co2=d_co2_monthly, g_pm25=d_pm_monthly),
        delta_breathe_daily_ug=delta_breathe_daily,
        explanation=Explanation(
            "Delta_emit = Emission(after) - Emission(before)",
            {
                "swap_id": swap_id,
                "units": units_per_day,
                "days": days_per_week,
                "co2": d_co2_monthly,
                "pm25": d_pm_monthly,
            },
            ["emission_factor", "in_vehicle_ratio", "inhalation_rate_daily_mean"],
            ["ARAI (2018)", "Goel & Kumar (2015)"],
            ["Linear scaling (4.33 weeks/month)"],
        ),
    )


def scale_to_community(
    swap_result: SwapImpactResult, households: int, participation_rate: float
) -> CommunityImpactResult:
    """Scale a household swap delta to community (Mohalla) level linearly."""
    if households < 0:
        raise ValueError(f"households must be non-negative, got {households}")
    if not (0.0 <= participation_rate <= 1.0):
        raise ValueError(
            f"participation_rate must be between 0.0 and 1.0, got {participation_rate}"
        )

    eff = float(households) * participation_rate
    co2_monthly, pm25_monthly = (
        round(swap_result.delta_emit_monthly.kg_co2 * eff, 2),
        round(swap_result.delta_emit_monthly.g_pm25 * eff, 2),
    )
    monthly_dose_mg = round(
        (max(0.0, -swap_result.delta_breathe_daily_ug) * 30.0 * eff) / 1000.0, 2
    )

    return CommunityImpactResult(
        households=households,
        participation_rate=participation_rate,
        community_delta_co2_kg_monthly=co2_monthly,
        community_delta_pm25_g_monthly=pm25_monthly,
        community_avoided_dose_monthly_mg=monthly_dose_mg,
        explanation=Explanation(
            "Community_Impact = Per_Household_Impact * Households * ParticipationRate",
            {
                "households": households,
                "participation_rate": participation_rate,
                "community_co2_monthly": co2_monthly,
            },
            ["emission_factor"],
            ["Mohalla linear aggregation model"],
            ["Independent adoption across units"],
        ),
    )
