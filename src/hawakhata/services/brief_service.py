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

SEVERE_PM25_THRESHOLD = 250.0
POOR_PM25_THRESHOLD = 120.0
VERY_POOR_PM25_THRESHOLD = 150.0
DEFAULT_ROOM_VOLUME_M3 = 60.0
DEFAULT_EARLIEST_START = 6
DEFAULT_LATEST_END = 20


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


def _normalize_members(profile: FamilyProfileInput | dict[str, Any]) -> list[dict[str, Any]]:
    p_dict = profile.model_dump() if isinstance(profile, FamilyProfileInput) else profile
    res: list[dict[str, Any]] = []
    for m in p_dict.get("members", []):
        raw_b = m.get("schedule_blocks") or m.get("schedule", [])
        norm_b = [
            {
                "start_hour": int(b.get("start_hour", 0)),
                "end_hour": int(b.get("end_hour", 1)),
                "micro_env": str(b.get("micro_env") or b.get("environment", "indoor_home")),
                "activity": str(b.get("activity", "other")),
                "label": str(b.get("label", "")),
                "flexible": bool(b.get("flexible", False)),
                "earliest_start": b.get("earliest_start"),
                "latest_end": b.get("latest_end"),
            }
            for b in raw_b
        ]
        res.append(
            {
                "id": str(m.get("id", "m")),
                "name": str(m.get("name") or m.get("label", "Member")),
                "age_band": str(m.get("age_band", "adult")),
                "sensitivities": list(m.get("sensitivities", [])),
                "schedule_blocks": norm_b,
            }
        )
    return res


def detect_forecast_shift(
    old_series: list[float],
    new_series: list[float],
    threshold_ug_m3: float = 40.0,
) -> bool:
    """Return True if maximum point difference between forecasts exceeds threshold."""
    if not old_series or not new_series:
        return False
    min_len = min(len(old_series), len(new_series))
    if min_len == 0:
        return False
    diff = max(abs(new_series[i] - old_series[i]) for i in range(min_len))
    return diff >= threshold_ug_m3


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
                e_val = (
                    int(b["earliest_start"])
                    if b.get("earliest_start") is not None
                    else DEFAULT_EARLIEST_START
                )
                l_val = (
                    int(b["latest_end"]) if b.get("latest_end") is not None else DEFAULT_LATEST_END
                )
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
                fixed_b.append(
                    ScheduleBlock(
                        start_hour=start,
                        end_hour=end,
                        micro_env=env,
                        activity="light",
                        label=act,
                    )
                )

        if flex_acts:
            opt = optimise_day_plan(
                age_band=age_band,
                fixed_blocks=fixed_b,
                flexible_activities=flex_acts,
                outdoor_pm25_series=new_series[:24],
            )
            if opt.total_savings_ug > 0:
                replan_notes.append(
                    f"Forecast changed by {max_diff:.0f} µg/m³. Rescheduled "
                    f"{m_name}'s flexible activities, saving {opt.total_savings_ug:.1f} µg."
                )

    if not replan_notes:
        replan_notes.append(
            f"Forecast shifted by {max_diff:.0f} µg/m³; checked schedule for vulnerable windows."
        )

    return ReplanResult(True, round(max_diff, 1), True, replan_notes)


def _compute_cleanest_window(
    pts: list[HourlyAirPoint], pm25_vals: list[float]
) -> tuple[str, float]:
    best_start = 0
    best_avg = float("inf")
    for i in range(len(pm25_vals) - 1):
        win_avg = (pm25_vals[i] + pm25_vals[i + 1]) / 2.0
        if win_avg < best_avg:
            best_avg = win_avg
            best_start = i
    end_idx = min(len(pts) - 1, best_start + 2)
    win_str = f"{pts[best_start].time_local}-{pts[end_idx].time_local}"
    win_pm = round(best_avg if best_avg < float("inf") else 0.0, 1)
    return win_str, win_pm


def _build_sensitive_alerts(
    members_data: list[dict[str, Any]], worst_hour: str, worst_pm25: float
) -> list[SensitiveAlertItem]:
    alerts: list[SensitiveAlertItem] = []
    for m in members_data:
        m_id, m_name, age = str(m["id"]), str(m["name"]), str(m["age_band"])
        sens = list(m["sensitivities"])
        if age in ("child", "elderly") or sens:
            sev: Literal["advisory", "warning", "critical"] = "advisory"
            if worst_pm25 > SEVERE_PM25_THRESHOLD:
                sev = "critical"
            elif worst_pm25 > POOR_PM25_THRESHOLD:
                sev = "warning"
            reasons: list[str] = []
            if age == "child":
                reasons.append("developing lungs")
            if age == "elderly":
                reasons.append("respiratory vulnerability")
            reasons.extend(sens)
            alerts.append(
                SensitiveAlertItem(
                    member_id=m_id,
                    name=m_name,
                    alert_text=(
                        f"Smog peak around {worst_hour} ({worst_pm25} µg/m³). Protect "
                        f"{m_name} ({', '.join(reasons)}) indoors with air filtration."
                    ),
                    severity=sev,
                )
            )
    return alerts


def _build_top_actions(
    pm25_vals: list[float], worst_pm25: float, cleanest_win: str, cleanest_pm: float
) -> list[BriefActionItem]:
    actions: list[BriefActionItem] = []
    ranked_hacks = rank_indoor_hacks(
        room_volume_m3=DEFAULT_ROOM_VOLUME_M3, outdoor_series=pm25_vals, baseline_events=[]
    )
    if ranked_hacks:
        top_hack = ranked_hacks[0]
        actions.append(
            BriefActionItem(
                title=f"Indoor Air Hack: {top_hack.title}",
                description=(
                    f"{top_hack.advice} (Reduces PM2.5 by {top_hack.delta_pm25_ug_m3:.1f} µg/m³)."
                ),
                ug_saved=round(max(0.0, top_hack.delta_pm25_ug_m3 * 10.0), 1),
                action_type="indoor_hack",
            )
        )
    metro_swap = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    g_saved = abs(metro_swap.delta_emit_daily.g_pm25)
    actions.append(
        BriefActionItem(
            title="Clean Commute: Switch to Metro",
            description=f"Eliminate {g_saved:.1f} g of direct PM2.5 emissions per commute.",
            ug_saved=round(abs(metro_swap.delta_breathe_daily_ug), 1),
            action_type="swap",
        )
    )
    actions.append(
        BriefActionItem(
            title="Outdoor Window Shift",
            description=(
                f"Shift outdoor activity to clean window ({cleanest_win}, ~{cleanest_pm} µg/m³)."
            ),
            ug_saved=round(max(0.0, worst_pm25 - cleanest_pm) * 5.0, 1),
            action_type="planner_window",
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
    worst_hour_local = pts[worst_idx].time_local
    worst_pm25 = round(pm25_vals[worst_idx], 1)
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
        f"Severe smog today peaking at {worst_hour_local} ({worst_pm25} µg/m³). "
        f"Cleanest air window is {cleanest_win}."
        if worst_pm25 > VERY_POOR_PM25_THRESHOLD
        else f"Moderate pollution today with peak {worst_pm25} µg/m³ at {worst_hour_local}."
    )

    explanation = Explanation(
        formula="brief = worst_hour(series) + cleanest_window(series) + rank_hacks() + swaps()",
        inputs={
            "worst_hour_local": worst_hour_local,
            "worst_pm25": worst_pm25,
            "cleanest_window": cleanest_win,
            "cleanest_pm25": cleanest_pm,
            "points_count": len(pts),
        },
        constants_used=[],
        sources=["CPCB National Air Quality Index", "Google Maps Platform Air Quality API"],
        assumptions=["Outdoor hourly forecast represents local breathing environment."],
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
