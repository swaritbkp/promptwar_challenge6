"""Domain tools for HawaKhata agent wrapping engine and integration services."""

from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass
from typing import Any

from hawakhata.api.schemas import (
    FamilyProfileInput,
    FlexibleActivityInput,
    LocationInput,
    RoomInput,
    SwapsImpactRequest,
)
from hawakhata.engine.constants import load_constants
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.services.brief_service import generate_morning_brief
from hawakhata.services.indoor_service import simulate_indoor_environment
from hawakhata.services.passbook_service import compute_family_passbook
from hawakhata.services.planner_service import compute_optimized_plan
from hawakhata.services.swap_service import compute_swap_impact

MIN_ISO_HOUR_LEN = 13


@dataclass
class ToolContext:
    """Context holding family profile, location, and AQ client for tools."""

    profile: FamilyProfileInput
    location: LocationInput
    aq_client: AirQualityClient
    date_iso: str = "2026-11-18"


_current_tool_context: contextvars.ContextVar[ToolContext | None] = contextvars.ContextVar(
    "current_tool_context", default=None
)


def get_current_context() -> ToolContext:
    """Retrieve active tool execution context."""
    ctx = _current_tool_context.get()
    if ctx is None:
        raise RuntimeError("No active ToolContext found in current context")
    return ctx


def set_current_context(ctx: ToolContext) -> contextvars.Token[ToolContext | None]:
    """Set active tool context for current async task."""
    return _current_tool_context.set(ctx)


def reset_current_context(token: contextvars.Token[ToolContext | None]) -> None:
    """Reset active tool context."""
    _current_tool_context.reset(token)


async def get_air_forecast(hours: int = 24) -> dict[str, Any]:
    """Get hourly ambient air quality forecast and NAQI categories."""
    ctx = get_current_context()
    series = await ctx.aq_client.get_hourly_forecast(
        lat=ctx.location.lat, lng=ctx.location.lng, hours=min(hours, 96)
    )
    hourly = [
        {
            "hour": int(p.time_local[11:13]) if len(p.time_local) >= MIN_ISO_HOUR_LEN else 0,
            "pm25_ug_m3": round(p.pm25_ug_m3, 1),
            "aqi": p.aqi_local,
            "category": p.category_local,
        }
        for p in series.points
    ]
    cur = series.points[0] if series.points else None
    return {
        "result": {
            "city": ctx.location.city_name,
            "current_pm25": round(cur.pm25_ug_m3, 1) if cur else 0.0,
            "current_aqi": cur.aqi_local if cur else 0,
            "category": cur.category_local if cur else "Moderate",
            "hourly": hourly,
        },
        "explanation": "Google Maps Air Quality API hourly forecast normalized to India NAQI.",
        "missing_fields": [],
    }


async def get_family_passbook(date_iso: str | None = None) -> dict[str, Any]:
    """Compute daily air passbook (debit, savings, budget, balance, cigarette equivalent)."""
    ctx = get_current_context()
    series = await ctx.aq_client.get_hourly_forecast(
        lat=ctx.location.lat, lng=ctx.location.lng, hours=24
    )
    outdoor_pm25 = [p.pm25_ug_m3 for p in series.points]
    pb = compute_family_passbook(profile=ctx.profile, outdoor_pm25_series=outdoor_pm25)
    cigs = round(sum(float(e.get("cigarette_equivalent", 0.0)) for e in pb.entries), 1)
    members_list = [
        {
            "name": str(e.get("member_label", "Member")),
            "age_band": str(e.get("age_band", "adult")),
            "debit_ug": round(float(e.get("debit_ug", 0.0)), 1),
            "budget_ug": round(float(e.get("budget_ug", 0.0)), 1),
            "balance_ug": round(float(e.get("balance_ug", 0.0)), 1),
            "cigarettes": round(float(e.get("cigarette_equivalent", 0.0)), 1),
        }
        for e in pb.entries
    ]
    return {
        "result": {
            "date": date_iso or ctx.date_iso,
            "total_debit_ug": round(pb.total_debit_ug, 1),
            "total_budget_ug": round(pb.total_budget_ug, 1),
            "net_balance_ug": round(pb.net_balance_ug, 1),
            "status": "within budget" if pb.net_balance_ug >= 0 else "exceeded budget",
            "cigarette_equivalent": cigs,
            "members": members_list,
        },
        "explanation": "WHO 2021 air budget and Berkeley Earth cigarette equivalence.",
        "missing_fields": [],
    }


async def plan_clean_windows(
    activities_json: str | None = None, member_id: str | None = None
) -> dict[str, Any]:
    """Find schedule allocations that minimize personal particulate exposure."""
    if not activities_json or activities_json.strip() in ("", "[]", "{}"):
        return {
            "result": None,
            "explanation": "Flexible activity details needed to optimize clean windows.",
            "missing_fields": ["activity_name", "duration_min", "preferred_window"],
        }
    try:
        data = json.loads(activities_json)
        if not isinstance(data, list):
            data = [data]
    except Exception:
        return {
            "result": None,
            "explanation": "Malformed activities JSON.",
            "missing_fields": ["activities_json"],
        }

    ctx = get_current_context()
    target_mid = member_id or (ctx.profile.members[0].id if ctx.profile.members else "member_0")
    activities = [
        FlexibleActivityInput(
            id=f"act_{idx}",
            member_id=target_mid,
            title=str(item.get("name") or item.get("title") or "Flexible Activity"),
            duration_hours=max(
                1, int(item.get("duration_minutes") or item.get("duration_min") or 60) // 60
            ),
            earliest_start_hour=int(
                item.get("earliest_start_hour") or item.get("earliest_hour") or 6
            ),
            latest_start_hour=int(item.get("latest_start_hour") or item.get("latest_hour") or 10),
            micro_env=str(item.get("micro_env") or item.get("location_type") or "outdoor"),
            activity=str(item.get("activity") or item.get("activity_intensity") or "moderate"),
            usual_start_hour=int(item.get("usual_start_hour") or item.get("earliest_hour") or 7),
        )
        for idx, item in enumerate(data)
        if isinstance(item, dict)
    ]
    series = await ctx.aq_client.get_hourly_forecast(
        lat=ctx.location.lat, lng=ctx.location.lng, hours=24
    )
    plan_res = compute_optimized_plan(
        profile=ctx.profile,
        member_id=target_mid,
        flexible_activities=activities,
        outdoor_pm25_series=[p.pm25_ug_m3 for p in series.points],
    )
    shifts = [
        {
            "activity": s.title,
            "usual_start": f"{s.usual_start_hour:02d}:00",
            "recommended_start": f"{s.optimized_start_hour:02d}:00",
            "savings_ug": round(s.savings_ug, 1),
            "percent_savings": round(s.percent_savings, 1),
        }
        for s in plan_res.shifts
    ]
    return {
        "result": {
            "member_id": target_mid,
            "total_savings_ug": round(plan_res.total_savings_ug, 1),
            "usual_dose_ug": round(plan_res.usual_dose_ug, 1),
            "optimized_dose_ug": round(plan_res.optimized_dose_ug, 1),
            "shifts": shifts,
        },
        "explanation": "Combinatorial non-colliding window optimization using Monte Carlo paths.",
        "missing_fields": [],
    }


async def simulate_indoor_air(
    room_name: str | None = None, interventions: list[str] | None = None
) -> dict[str, Any]:
    """Simulate single-zone indoor PM2.5 under purifier and window interventions."""
    ctx = get_current_context()
    target_room = (
        next((r for r in ctx.profile.rooms if r.name == room_name), None)
        if room_name
        else (ctx.profile.rooms[0] if ctx.profile.rooms else None)
    )
    if target_room is None:
        target_room = RoomInput(
            name=room_name or "Living Room",
            volume_m3=50.0,
            purifier_cadr_m3_per_h=300.0,
            windows_open_hours=[12, 13],
            purifier_on_hours=list(range(24)),
        )
    series = await ctx.aq_client.get_hourly_forecast(
        lat=ctx.location.lat, lng=ctx.location.lng, hours=24
    )
    sim = simulate_indoor_environment(
        room=target_room,
        sources=ctx.profile.sources,
        outdoor_pm25_series=[p.pm25_ug_m3 for p in series.points],
    )
    mean_pm25 = round(float(sim.simulation.get("mean_pm25_ug_m3", 0.0)), 1)
    peak_pm25 = round(float(sim.simulation.get("peak_pm25_ug_m3", 0.0)), 1)
    return {
        "result": {
            "room_name": sim.room_name,
            "mean_pm25_ug_m3": mean_pm25,
            "peak_pm25_ug_m3": peak_pm25,
            "purifier_cadr_needed_m3_h": sim.purifier_recommendation.get(
                "required_cadr_m3_per_h", 0.0
            ),
            "ventilation_safe_hours": sim.ventilation_recommendation.get("recommended_hours", []),
        },
        "explanation": "Single-zone mass-balance ODE with exact exponential integration.",
        "missing_fields": [],
    }


async def evaluate_swaps(
    swap_id: str = "commute_car_to_metro", households: int = 1
) -> dict[str, Any]:
    """Calculate emission and exposure reductions from sustainable household swaps."""
    ctx = get_current_context()
    series = await ctx.aq_client.get_hourly_forecast(
        lat=ctx.location.lat, lng=ctx.location.lng, hours=24
    )
    mean_outdoor = (
        sum(p.pm25_ug_m3 for p in series.points) / len(series.points) if series.points else 150.0
    )
    res = compute_swap_impact(
        req=SwapsImpactRequest(swap_id=swap_id, units_per_day=1.0, households=households),
        outdoor_pm25_mean=mean_outdoor,
    )
    hh, comm = res.household, res.community
    d_m = hh.get("delta_emit_monthly", {})
    co2 = abs(float(d_m.get("kg_co2", 0.0))) if isinstance(d_m, dict) else 0.0
    return {
        "result": {
            "title": str(hh.get("title", swap_id)),
            "total_emissions_avoided_kg": round(co2, 2),
            "total_exposure_saved_ug": round(abs(float(hh.get("delta_breathe_daily_ug", 0.0))), 1),
            "community_households": int(comm.get("households", households)),
            "community_emissions_avoided_kg": round(
                abs(float(comm.get("community_delta_co2_kg_monthly", 0.0))), 2
            ),
        },
        "explanation": "Deterministic activity emission factors scaled linearly to community.",
        "missing_fields": [],
    }


async def get_smog_brief() -> dict[str, Any]:
    """Generate proactive morning brief with cleanest windows and member alerts."""
    ctx = get_current_context()
    series = await ctx.aq_client.get_hourly_forecast(
        lat=ctx.location.lat, lng=ctx.location.lng, hours=24
    )
    brief = generate_morning_brief(profile=ctx.profile, air_series=series)
    cur_pm = round(series.points[0].pm25_ug_m3, 1) if series.points else 0.0
    cur_aqi = series.points[0].aqi_local if series.points else 0
    parts = str(brief.cleanest_window_local).split("-")
    return {
        "result": {
            "city": ctx.location.city_name,
            "headline": brief.headline,
            "current_pm25": cur_pm,
            "current_aqi": cur_aqi,
            "cleanest_window": {
                "start": parts[0] if parts else "12:00",
                "end": parts[1] if len(parts) > 1 else "15:00",
                "pm25": round(brief.cleanest_pm25, 1),
            },
            "member_alerts": [
                {"name": a.name, "message": a.alert_text} for a in brief.sensitive_member_alerts
            ],
        },
        "explanation": "Daily proactive smog brief aggregating forecast and vulnerability rules.",
        "missing_fields": [],
    }


async def explain_number(metric_id: str) -> dict[str, Any]:
    """Explain provenance, scientific source, and calculation method for a metric."""
    constants = load_constants()
    clean_id = metric_id.lower().strip()
    if clean_id in constants:
        c = constants[clean_id]
        return {
            "result": {
                "name": c.id,
                "value": c.value,
                "unit": c.unit,
                "source": c.source,
                "method": f"Verified constant for {c.applies_to}",
            },
            "explanation": f"Scientific source and methodology for {c.id}.",
            "missing_fields": [],
        }

    exps = {
        "daily_budget": {
            "name": "WHO 24-Hour PM2.5 Guideline Budget",
            "value": 15.0,
            "unit": "ug/m3",
            "source": "WHO Air Quality Guidelines 2021",
            "method": "15 ug/m3 * 24h breathing volume.",
        },
        "pm25_cigarette": {
            "name": "Berkeley Earth Cigarette Equivalence",
            "value": 22.0,
            "unit": "ug/m3 per cigarette",
            "source": "Berkeley Earth 2015",
            "method": "22 ug/m3 24h approx 1 cigarette.",
        },
        "naqi": {
            "name": "India National Air Quality Index (NAQI)",
            "value": 6,
            "unit": "categories",
            "source": "CPCB 2014 NAQI",
            "method": "Linear interpolation across breakpoints.",
        },
    }
    match = exps.get(
        clean_id,
        {
            "name": metric_id,
            "value": 0.0,
            "unit": "unit",
            "source": "HawaKhata Knowledge Base",
            "method": "Pure deterministic calculation.",
        },
    )
    return {"result": match, "explanation": f"Provenance for {metric_id}", "missing_fields": []}


ALL_TOOLS = [
    get_air_forecast,
    get_family_passbook,
    plan_clean_windows,
    simulate_indoor_air,
    evaluate_swaps,
    get_smog_brief,
    explain_number,
]
