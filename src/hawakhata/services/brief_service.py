"""Proactive morning brief service with forecast-shift detection and automatic re-planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from hawakhata.api.schemas import FamilyProfileInput, ForecastShiftInfo
from hawakhata.engine.dose import ScheduleBlock
from hawakhata.engine.explain import Explanation
from hawakhata.engine.planner import FlexibleActivity, optimise_day_plan
from hawakhata.engine.recommendations import rank_indoor_hacks
from hawakhata.engine.swaps import evaluate_swap
from hawakhata.integrations.air_quality import HourlyAirPoint, HourlyAirSeries


@dataclass(frozen=True)
class BriefActionItem:
    """Action recommendation with quantified exposure savings."""

    title: str
    description: str
    ug_saved: float
    action_type: Literal["indoor_hack", "planner_window", "swap"]


@dataclass(frozen=True)
class SensitiveAlertItem:
    """Targeted alert for a vulnerable individual."""

    member_id: str
    name: str
    alert_text: str
    severity: Literal["advisory", "warning", "critical"]


@dataclass(frozen=True)
class ReplanResult:
    """Outcome of a forecast shift re-plan check."""

    shifted: bool
    delta_max_pm25: float
    replanned: bool
    replan_notes: list[str]


@dataclass(frozen=True)
class BriefResult:
    """Proactive morning brief output."""

    headline: str
    worst_hour_local: str
    worst_pm25: float
    cleanest_window_local: str
    cleanest_pm25: float
    sensitive_member_alerts: list[SensitiveAlertItem]
    top_actions: list[BriefActionItem]
    forecast_shift: ForecastShiftInfo | None
    explanation: Explanation


def _norm_block(b: dict[str, Any]) -> dict[str, Any]:
    w = b.get("window", [6, 19]) if b.get("window") else None
    return {
        "start_hour": int(b.get("start_hour", b.get("start", 0))),
        "end_hour": int(b.get("end_hour", b.get("end", 1))),
        "micro_env": str(b.get("micro_env") or b.get("environment", "indoor_home")),
        "activity": str(b.get("activity", "other")),
        "label": str(b.get("label", b.get("note", ""))),
        "flexible": bool(b.get("flexible", not b.get("fixed", True))),
        "earliest_start": b.get("earliest_start", w[0] if w else None),
        "latest_end": b.get("latest_end", w[1] if w else None),
    }


def _normalize_members(profile: FamilyProfileInput | dict[str, Any]) -> list[dict[str, Any]]:
    p = profile.model_dump() if isinstance(profile, FamilyProfileInput) else profile
    return [
        {
            "id": str(m.get("id", "m")),
            "name": str(m.get("name") or m.get("label", "Member")),
            "age_band": str(m.get("age_band", "adult")),
            "sensitivities": list(m.get("sensitivities", [])),
            "schedule_blocks": [
                _norm_block(b) for b in (m.get("schedule_blocks") or m.get("schedule", []))
            ],
        }
        for m in p.get("members", [])
    ]


def detect_forecast_shift(
    old_series: list[float], new_series: list[float], threshold_ug_m3: float = 40.0
) -> bool:
    """Return True if maximum point difference between forecasts exceeds threshold."""
    if not old_series or not new_series:
        return False
    min_len = min(len(old_series), len(new_series))
    return (
        False
        if min_len == 0
        else max(abs(new_series[i] - old_series[i]) for i in range(min_len)) >= threshold_ug_m3
    )


def replan_if_needed(
    profile: FamilyProfileInput | dict[str, Any],
    old_series: list[float],
    new_series: list[float],
    threshold_ug_m3: float = 40.0,
) -> ReplanResult:
    """Check forecast shift and re-optimize flexible schedule blocks if significant."""
    shifted = detect_forecast_shift(old_series, new_series, threshold_ug_m3)
    min_len = min(len(old_series), len(new_series))
    max_diff = (
        max(abs(new_series[i] - old_series[i]) for i in range(min_len)) if min_len > 0 else 0.0
    )
    if not shifted:
        return ReplanResult(False, round(max_diff, 1), False, [])

    replan_notes: list[str] = []
    for m in _normalize_members(profile):
        m_name, age_band = str(m["name"]), str(m["age_band"])
        fixed_b: list[ScheduleBlock] = []
        flex_acts: list[FlexibleActivity] = []
        for b in m["schedule_blocks"]:
            is_flex, act = bool(b.get("flexible", False)), str(b.get("activity", "other"))
            start, end = int(b.get("start_hour", 0)), int(b.get("end_hour", 1))
            env = str(b.get("micro_env", "indoor_home"))
            if is_flex:
                dur = max(1, end - start)
                e_val = int(b["earliest_start"]) if b.get("earliest_start") is not None else 6
                l_val = int(b["latest_end"]) if b.get("latest_end") is not None else 20
                flex_acts.append(
                    FlexibleActivity(
                        id=f"flex_{len(flex_acts)}",
                        member_id=str(m["id"]),
                        title=str(b.get("label", act)),
                        duration_hours=dur,
                        earliest_start_hour=e_val,
                        latest_start_hour=max(e_val, l_val - dur),
                        micro_env=env,
                        activity=act,
                        usual_start_hour=start,
                    )
                )
            else:
                fixed_b.append(ScheduleBlock(start, end, env, "light", act))

        if flex_acts:
            opt = optimise_day_plan(
                age_band=age_band,
                fixed_blocks=fixed_b,
                flexible_activities=flex_acts,
                outdoor_pm25_series=new_series[:24],
            )
            if opt.total_savings_ug > 0:
                replan_notes.append(
                    f"Forecast changed by {max_diff:.0f} µg/m³. Rescheduled {m_name}, saving {opt.total_savings_ug:.1f} µg."
                )

    if not replan_notes:
        replan_notes.append(f"Forecast shifted by {max_diff:.0f} µg/m³; checked schedule.")
    return ReplanResult(True, round(max_diff, 1), True, replan_notes)


def _compute_cleanest_window(
    pts: list[HourlyAirPoint], pm25_vals: list[float]
) -> tuple[str, float]:
    best_start, best_avg = 0, float("inf")
    for i in range(len(pm25_vals) - 1):
        win_avg = (pm25_vals[i] + pm25_vals[i + 1]) / 2.0
        if win_avg < best_avg:
            best_avg, best_start = win_avg, i
    end_idx = min(len(pts) - 1, best_start + 2)
    return f"{pts[best_start].time_local}-{pts[end_idx].time_local}", round(
        best_avg if best_avg < float("inf") else 0.0, 1
    )


def _build_sensitive_alerts(
    members_data: list[dict[str, Any]], worst_hour: str, worst_pm25: float
) -> list[SensitiveAlertItem]:
    alerts: list[SensitiveAlertItem] = []
    for m in members_data:
        m_id, m_name, age = str(m["id"]), str(m["name"]), str(m["age_band"])
        sens = list(m["sensitivities"])
        if age in ("child", "elderly") or sens:
            sev: Literal["advisory", "warning", "critical"] = (
                "critical"
                if worst_pm25 > 250.0
                else ("warning" if worst_pm25 > 120.0 else "advisory")
            )
            reasons = ([age] if age in ("child", "elderly") else []) + sens
            alerts.append(
                SensitiveAlertItem(
                    member_id=m_id,
                    name=m_name,
                    alert_text=f"Smog peak around {worst_hour} ({worst_pm25} µg/m³). Protect {m_name} ({', '.join(reasons)}) indoors with air filtration.",
                    severity=sev,
                )
            )
    return alerts


def _build_top_actions(
    pm25_vals: list[float], worst_pm25: float, cleanest_win: str, cleanest_pm: float
) -> list[BriefActionItem]:
    actions: list[BriefActionItem] = []
    hacks = rank_indoor_hacks(room_volume_m3=60.0, outdoor_series=pm25_vals, baseline_events=[])
    if hacks:
        top = hacks[0]
        actions.append(
            BriefActionItem(
                f"Indoor Air Hack: {top.title}",
                f"{top.advice} (Reduces PM2.5 by {top.delta_pm25_ug_m3:.1f} µg/m³).",
                round(max(0.0, top.delta_pm25_ug_m3 * 10.0), 1),
                "indoor_hack",
            )
        )
    metro = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    actions.append(
        BriefActionItem(
            "Clean Commute: Switch to Metro",
            f"Eliminate {abs(metro.delta_emit_daily.g_pm25):.1f} g PM2.5 per commute.",
            round(abs(metro.delta_breathe_daily_ug), 1),
            "swap",
        )
    )
    actions.append(
        BriefActionItem(
            "Outdoor Window Shift",
            f"Shift activity to clean window ({cleanest_win}, ~{cleanest_pm} µg/m³).",
            round(max(0.0, worst_pm25 - cleanest_pm) * 5.0, 1),
            "planner_window",
        )
    )
    return actions


def generate_morning_brief(
    profile: FamilyProfileInput | dict[str, Any],
    air_series: HourlyAirSeries,
    cached_yesterday_series: list[float] | None = None,
    threshold_ug_m3: float = 40.0,
) -> BriefResult:
    """Generate comprehensive morning brief from forecast and family profile."""
    pts = air_series.points
    if not pts:
        return BriefResult(
            headline="Air data unavailable for today.",
            worst_hour_local="12:00",
            worst_pm25=0.0,
            cleanest_window_local="12:00-14:00",
            cleanest_pm25=0.0,
            sensitive_member_alerts=[],
            top_actions=[],
            forecast_shift=None,
            explanation=Explanation("empty_series", {}, [], [], ["No air points returned"]),
        )

    pm25_vals = [pt.pm25_ug_m3 for pt in pts[:24]]
    worst_idx = max(range(len(pm25_vals)), key=lambda i: pm25_vals[i])
    worst_hour_local, worst_pm25 = pts[worst_idx].time_local, round(pm25_vals[worst_idx], 1)
    cleanest_win, cleanest_pm = _compute_cleanest_window(pts, pm25_vals)
    alerts = _build_sensitive_alerts(_normalize_members(profile), worst_hour_local, worst_pm25)
    actions = _build_top_actions(pm25_vals, worst_pm25, cleanest_win, cleanest_pm)

    shift_info: ForecastShiftInfo | None = None
    if cached_yesterday_series:
        replan = replan_if_needed(profile, cached_yesterday_series, pm25_vals, threshold_ug_m3)
        shift_info = ForecastShiftInfo(
            shifted=replan.shifted,
            delta_max_pm25=replan.delta_max_pm25,
            replanned=replan.replanned,
            note="; ".join(replan.replan_notes) if replan.replan_notes else "No shift detected.",
        )

    headline = (
        f"Severe smog today peaking at {worst_hour_local} ({worst_pm25} µg/m³). Cleanest air window is {cleanest_win}."
        if worst_pm25 > 150.0
        else f"Moderate pollution today with peak {worst_pm25} µg/m³ at {worst_hour_local}."
    )

    explanation = Explanation(
        formula="brief = worst_hour(series) + cleanest_window(series) + rank_hacks() + swaps()",
        inputs={
            "worst_hour": worst_hour_local,
            "worst_pm25": worst_pm25,
            "cleanest_win": cleanest_win,
        },
        constants_used=[],
        sources=["CPCB NAQI", "Google Maps AQ API"],
        assumptions=["Outdoor forecast represents breathing environment."],
    )

    return BriefResult(
        headline=headline,
        worst_hour_local=worst_hour_local,
        worst_pm25=worst_pm25,
        cleanest_window_local=cleanest_win,
        cleanest_pm25=cleanest_pm,
        sensitive_member_alerts=alerts,
        top_actions=actions,
        forecast_shift=shift_info,
        explanation=explanation,
    )
