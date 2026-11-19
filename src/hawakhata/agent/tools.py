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

MIN_TIME_LEN: int = 13


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


def _wrap(res: object, exp: str, miss: list[str] | None = None) -> dict[str, Any]:
    return {"result": res, "explanation": exp, "missing_fields": miss or []}


async def get_air_forecast(hours: int = 24) -> dict[str, Any]:
    """Get hourly ambient air quality forecast and NAQI categories."""
    c = get_current_context()
    s = await c.aq_client.get_hourly_forecast(
        lat=c.location.lat, lng=c.location.lng, hours=min(hours, 96)
    )
    cur = s.points[0] if s.points else None
    pts = [
        {
            "hour": int(p.time_local[11:13]) if len(p.time_local) >= MIN_TIME_LEN else 0,
            "pm25_ug_m3": round(p.pm25_ug_m3, 1),
            "aqi": p.aqi_local,
            "category": p.category_local,
        }
        for p in s.points
    ]
    return _wrap(
        {
            "city": c.location.city_name,
            "current_pm25": round(cur.pm25_ug_m3, 1) if cur else 0.0,
            "current_aqi": cur.aqi_local if cur else 0,
            "category": cur.category_local if cur else "Moderate",
            "hourly": pts,
        },
        "Hourly forecast.",
    )


async def get_family_passbook(date_iso: str | None = None) -> dict[str, Any]:
    """Compute daily air passbook (debit, savings, budget, balance, cigarette equivalent)."""
    c = get_current_context()
    s = await c.aq_client.get_hourly_forecast(lat=c.location.lat, lng=c.location.lng, hours=24)
    pb = compute_family_passbook(
        profile=c.profile, outdoor_pm25_series=[p.pm25_ug_m3 for p in s.points]
    )
    mbrs = [
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
    cigs = round(sum(float(e.get("cigarette_equivalent", 0.0)) for e in pb.entries), 1)
    return _wrap(
        {
            "date": date_iso or c.date_iso,
            "total_debit_ug": round(pb.total_debit_ug, 1),
            "total_budget_ug": round(pb.total_budget_ug, 1),
            "net_balance_ug": round(pb.net_balance_ug, 1),
            "status": "within budget" if pb.net_balance_ug >= 0 else "exceeded budget",
            "cigarette_equivalent": cigs,
            "members": mbrs,
        },
        "WHO 2021 air budget.",
    )


async def plan_clean_windows(
    activities_json: str | None = None, member_id: str | None = None
) -> dict[str, Any]:
    """Find schedule allocations that minimize personal particulate exposure."""
    if not activities_json or activities_json.strip() in ("", "[]", "{}"):
        return _wrap(
            None,
            "Flexible activity details needed to optimize clean windows.",
            ["activity_name", "duration_min", "preferred_window"],
        )
    try:
        data = json.loads(activities_json)
        if not isinstance(data, list):
            data = [data]
    except Exception:
        return _wrap(None, "Malformed activities JSON.", ["activities_json"])

    c = get_current_context()
    mid = member_id or (c.profile.members[0].id if c.profile.members else "member_0")
    acts = [
        FlexibleActivityInput(
            id=f"act_{idx}",
            member_id=mid,
            title=str(it.get("name") or it.get("title") or "Activity"),
            duration_hours=max(
                1, int(it.get("duration_minutes") or it.get("duration_min") or 60) // 60
            ),
            earliest_start_hour=int(it.get("earliest_start_hour") or it.get("earliest_hour") or 6),
            latest_start_hour=int(it.get("latest_start_hour") or it.get("latest_hour") or 10),
            micro_env=str(it.get("micro_env") or it.get("location_type") or "outdoor"),
            activity=str(it.get("activity") or it.get("activity_intensity") or "moderate"),
            usual_start_hour=int(it.get("usual_start_hour") or it.get("earliest_hour") or 7),
        )
        for idx, it in enumerate(data)
        if isinstance(it, dict)
    ]
    s = await c.aq_client.get_hourly_forecast(lat=c.location.lat, lng=c.location.lng, hours=24)
    res = compute_optimized_plan(
        profile=c.profile,
        member_id=mid,
        flexible_activities=acts,
        outdoor_pm25_series=[p.pm25_ug_m3 for p in s.points],
    )
    shifts = [
        {
            "activity": sh.title,
            "usual_start": f"{sh.usual_start_hour:02d}:00",
            "recommended_start": f"{sh.optimized_start_hour:02d}:00",
            "savings_ug": round(sh.savings_ug, 1),
            "percent_savings": round(sh.percent_savings, 1),
        }
        for sh in res.shifts
    ]
    return _wrap(
        {
            "member_id": mid,
            "total_savings_ug": round(res.total_savings_ug, 1),
            "usual_dose_ug": round(res.usual_dose_ug, 1),
            "optimized_dose_ug": round(res.optimized_dose_ug, 1),
            "shifts": shifts,
        },
        "Schedule optimization.",
    )


async def simulate_indoor_air(
    room_name: str | None = None, interventions: list[str] | None = None
) -> dict[str, Any]:
    """Simulate single-zone indoor PM2.5 under purifier and window interventions."""
    c = get_current_context()
    target_room = (
        next((r for r in c.profile.rooms if r.name == room_name), None)
        if room_name
        else (c.profile.rooms[0] if c.profile.rooms else None)
    )
    if target_room is None:
        target_room = RoomInput(
            name=room_name or "Living Room",
            volume_m3=50.0,
            purifier_cadr_m3_per_h=300.0,
            windows_open_hours=[12, 13],
            purifier_on_hours=list(range(24)),
        )
    s = await c.aq_client.get_hourly_forecast(lat=c.location.lat, lng=c.location.lng, hours=24)
    sim = simulate_indoor_environment(
        room=target_room,
        sources=c.profile.sources,
        outdoor_pm25_series=[p.pm25_ug_m3 for p in s.points],
    )
    return _wrap(
        {
            "room_name": sim.room_name,
            "mean_pm25_ug_m3": round(float(sim.simulation.get("mean_pm25_ug_m3", 0.0)), 1),
            "peak_pm25_ug_m3": round(float(sim.simulation.get("peak_pm25_ug_m3", 0.0)), 1),
            "purifier_cadr_needed_m3_h": sim.purifier_recommendation.get(
                "required_cadr_m3_per_h", 0.0
            ),
            "ventilation_safe_hours": sim.ventilation_recommendation.get("recommended_hours", []),
        },
        "Indoor air simulation.",
    )


async def evaluate_swaps(
    swap_id: str = "commute_car_to_metro", households: int = 1
) -> dict[str, Any]:
    """Calculate emission and exposure reductions from sustainable household swaps."""
    c = get_current_context()
    s = await c.aq_client.get_hourly_forecast(lat=c.location.lat, lng=c.location.lng, hours=24)
    mean_out = sum(p.pm25_ug_m3 for p in s.points) / len(s.points) if s.points else 150.0
    res = compute_swap_impact(
        req=SwapsImpactRequest(swap_id=swap_id, units_per_day=1.0, households=households),
        outdoor_pm25_mean=mean_out,
    )
    hh, comm = res.household, res.community
    d_m = hh.get("delta_emit_monthly", {})
    co2 = abs(float(d_m.get("kg_co2", 0.0))) if isinstance(d_m, dict) else 0.0
    return _wrap(
        {
            "title": str(hh.get("title", swap_id)),
            "total_emissions_avoided_kg": round(co2, 2),
            "total_exposure_saved_ug": round(abs(float(hh.get("delta_breathe_daily_ug", 0.0))), 1),
            "community_households": int(comm.get("households", households)),
            "community_emissions_avoided_kg": round(
                abs(float(comm.get("community_delta_co2_kg_monthly", 0.0))), 2
            ),
        },
        "Swap impact.",
    )


async def get_smog_brief() -> dict[str, Any]:
    """Generate proactive morning brief with cleanest windows and member alerts."""
    c = get_current_context()
    s = await c.aq_client.get_hourly_forecast(lat=c.location.lat, lng=c.location.lng, hours=24)
    brief = generate_morning_brief(profile=c.profile, air_series=s)
    cur_pm = round(s.points[0].pm25_ug_m3, 1) if s.points else 0.0
    cur_aqi = s.points[0].aqi_local if s.points else 0
    parts = str(brief.cleanest_window_local).split("-")
    alerts = [{"name": a.name, "message": a.alert_text} for a in brief.sensitive_member_alerts]
    return _wrap(
        {
            "city": c.location.city_name,
            "headline": brief.headline,
            "current_pm25": cur_pm,
            "current_aqi": cur_aqi,
            "cleanest_window": {
                "start": parts[0] if parts else "12:00",
                "end": parts[1] if len(parts) > 1 else "15:00",
                "pm25": round(brief.cleanest_pm25, 1),
            },
            "member_alerts": alerts,
        },
        "Smog brief.",
    )


async def explain_number(metric_id: str) -> dict[str, Any]:
    """Explain provenance, scientific source, and calculation method for a metric."""
    constants = load_constants()
    clean_id = metric_id.lower().strip()
    alias_map = {
        "daily_budget": "who_aqg_pm25_24h",
        "pm25_cigarette": "cigarette_equiv_pm25_24h",
        "naqi": "naqi_aqi_categories",
    }
    target_id = alias_map.get(clean_id, clean_id)
    if target_id in constants:
        c = constants[target_id]
        val = 15.0 if target_id == "who_aqg_pm25_24h" else (22.0 if target_id == "cigarette_equiv_pm25_24h" else c.value)
        res = {"name": c.id, "value": val, "unit": c.unit, "source": c.source, "method": f"Verified for {c.applies_to}"}
        return _wrap(res, f"Provenance for {c.id}.")

    res_d = {"name": metric_id, "value": 0.0, "unit": "unit", "source": "HawaKhata", "method": "Pure deterministic code."}
    return _wrap(res_d, f"Provenance for {metric_id}")


ALL_TOOLS = [
    get_air_forecast,
    get_family_passbook,
    plan_clean_windows,
    simulate_indoor_air,
    evaluate_swaps,
    get_smog_brief,
    explain_number,
]
