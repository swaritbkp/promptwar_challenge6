"""Pure deterministic calculation engine for air passbook, dose, and indoor simulation."""

from __future__ import annotations

from hawakhata.engine.aqi import (
    NAQICategory,
    aqi_to_category,
    pm25_to_naqi_category,
    pm25_to_sub_index,
)
from hawakhata.engine.budget import (
    PassbookEntry,
    build_passbook_entry,
    daily_air_budget_ug,
)
from hawakhata.engine.constants import (
    ConstantValue,
    get_constant,
    load_constants,
)
from hawakhata.engine.dose import (
    DoseContributor,
    MemberDoseResult,
    ScheduleBlock,
    TimelineSlot,
    build_member_timeline,
    compute_member_dose,
    inhalation_rate_m3_per_h,
)
from hawakhata.engine.emissions import (
    ActivityEmissionsResult,
    EmissionValue,
    activity_emissions,
)
from hawakhata.engine.explain import Explanation
from hawakhata.engine.indoor_model import (
    IndoorSimulationResult,
    IndoorSourceEvent,
    simulate_indoor_pm25,
    steady_state_pm25,
)
from hawakhata.engine.planner import (
    FlexibleActivity,
    OptimizedPlanResult,
    PlannedShift,
    optimise_day_plan,
)
from hawakhata.engine.recommendations import (
    IndoorHack,
    PurifierRecommendation,
    VentilationRecommendation,
    rank_indoor_hacks,
    recommend_purifier_cadr,
    recommend_ventilation_hours,
)
from hawakhata.engine.swaps import (
    CommunityImpactResult,
    DeltaEmission,
    SwapImpactResult,
    evaluate_swap,
    get_available_swaps,
    scale_to_community,
)
from hawakhata.engine.uncertainty import p50_p90, sample_forecast_paths

__all__ = [
    "ActivityEmissionsResult",
    "CommunityImpactResult",
    "ConstantValue",
    "DeltaEmission",
    "DoseContributor",
    "EmissionValue",
    "Explanation",
    "FlexibleActivity",
    "IndoorHack",
    "IndoorSimulationResult",
    "IndoorSourceEvent",
    "MemberDoseResult",
    "NAQICategory",
    "OptimizedPlanResult",
    "PassbookEntry",
    "PlannedShift",
    "PurifierRecommendation",
    "ScheduleBlock",
    "SwapImpactResult",
    "TimelineSlot",
    "VentilationRecommendation",
    "activity_emissions",
    "aqi_to_category",
    "build_member_timeline",
    "build_passbook_entry",
    "compute_member_dose",
    "daily_air_budget_ug",
    "evaluate_swap",
    "get_available_swaps",
    "get_constant",
    "inhalation_rate_m3_per_h",
    "load_constants",
    "optimise_day_plan",
    "p50_p90",
    "pm25_to_naqi_category",
    "pm25_to_sub_index",
    "rank_indoor_hacks",
    "recommend_purifier_cadr",
    "recommend_ventilation_hours",
    "sample_forecast_paths",
    "scale_to_community",
    "simulate_indoor_pm25",
    "steady_state_pm25",
]
