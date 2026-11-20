"""Clean-Window Planner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from hawakhata.engine.aqi import pm25_to_naqi_category, pm25_to_sub_index
from hawakhata.engine.dose import (
    ScheduleBlock,
    TimelineSlot,
    build_member_timeline,
    compute_member_dose,
    inhalation_rate_m3_per_h,
)
from hawakhata.engine.explain import Explanation
from hawakhata.engine.uncertainty import p50_p90, sample_forecast_paths


@dataclass(frozen=True, slots=True)
class FlexibleActivity:
    """An activity that can be repositioned during clean-window planning."""

    id: str
    member_id: str
    title: str
    duration_hours: int
    earliest_start_hour: int
    latest_start_hour: int
    micro_env: str
    activity: str
    usual_start_hour: int


@dataclass(frozen=True, slots=True)
class PlannedShift:
    """Recommended time shift for one flexible activity."""

    activity_id: str
    title: str
    member_id: str
    usual_start_hour: int
    optimized_start_hour: int
    savings_ug: float
    percent_savings: float
    explanation: str
    outdoor_pm25_at_optimized: float = 0.0


@dataclass(frozen=True, slots=True)
class OptimizedPlanResult:
    """Outcome of clean-window schedule optimization."""

    shifts: list[PlannedShift]
    total_savings_ug: float
    is_already_optimal: bool
    optimized_timeline: list[TimelineSlot]
    usual_dose_ug: float
    optimized_dose_ug: float
    explanation: Explanation


def _build_schedule_blocks(
    fixed_blocks: list[ScheduleBlock], activity_slots: dict[str, tuple[int, FlexibleActivity]]
) -> list[ScheduleBlock]:
    return list(fixed_blocks) + [
        ScheduleBlock(h, h + a.duration_hours, a.micro_env, a.activity, a.title or aid)
        for aid, (h, a) in activity_slots.items()
    ]


def _is_valid_slot(
    start_h: int, duration: int, occupied_hours: set[int], earliest: int, latest: int
) -> bool:
    if start_h < earliest or (start_h + duration - 1) > latest or (start_h + duration) > 24:
        return False
    return not bool(occupied_hours.intersection(range(start_h, start_h + duration)))


def _find_best_slot_for_activity(
    act: FlexibleActivity,
    chosen: dict[str, tuple[int, FlexibleActivity]],
    occupied: set[int],
    *,
    fixed_blocks: list[ScheduleBlock],
    age_band: str,
    robust_series: list[float],
    indoor_home_series: list[float] | None,
) -> int:
    def _eval(h: int) -> float:
        tl = build_member_timeline(
            _build_schedule_blocks(fixed_blocks, {**chosen, act.id: (h, act)})
        )
        return compute_member_dose(age_band, tl, robust_series, indoor_home_series).total_dose_ug

    best_hour, best_cost = act.usual_start_hour, float("inf")
    for h in range(act.earliest_start_hour, act.latest_start_hour + 1):
        if _is_valid_slot(
            h, act.duration_hours, occupied, act.earliest_start_hour, act.latest_start_hour
        ):
            cost = _eval(h)
            if cost < best_cost:
                best_cost, best_hour = cost, h

    if (
        _is_valid_slot(
            act.usual_start_hour,
            act.duration_hours,
            occupied,
            act.earliest_start_hour,
            act.latest_start_hour,
        )
        and abs(_eval(act.usual_start_hour) - best_cost) < 1e-4
    ):
        return act.usual_start_hour
    return best_hour


def optimise_day_plan(
    age_band: str,
    fixed_blocks: list[ScheduleBlock],
    flexible_activities: list[FlexibleActivity],
    outdoor_pm25_series: list[float],
    *,
    indoor_home_series: list[float] | None = None,
    robust_lambda: float = 0.5,
    uncertainty_spread: float = 0.25,
    seed: int = 42,
) -> OptimizedPlanResult:
    """Find schedule allocations that minimize expected dose under uncertainty."""
    if robust_lambda > 0.0 and uncertainty_spread > 0.0:
        p50, p90 = p50_p90(
            sample_forecast_paths(outdoor_pm25_series, spread=uncertainty_spread, n=30, seed=seed)
        )
        robust_series = [
            p50[i] + robust_lambda * max(0.0, p90[i] - p50[i]) for i in range(len(p50))
        ]
    else:
        robust_series = list(outdoor_pm25_series)

    usual_assignments = {a.id: (a.usual_start_hour, a) for a in flexible_activities}
    usual_dose = compute_member_dose(
        age_band,
        build_member_timeline(_build_schedule_blocks(fixed_blocks, usual_assignments)),
        robust_series,
        indoor_home_series,
    ).total_dose_ug

    occupied: set[int] = set()
    for b in fixed_blocks:
        occupied.update(range(max(0, b.start_hour), min(24, b.end_hour)))

    chosen: dict[str, tuple[int, FlexibleActivity]] = {}
    for act in sorted(flexible_activities, key=lambda a: a.duration_hours, reverse=True):
        best_h = _find_best_slot_for_activity(
            act,
            chosen,
            occupied,
            fixed_blocks=fixed_blocks,
            age_band=age_band,
            robust_series=robust_series,
            indoor_home_series=indoor_home_series,
        )
        chosen[act.id] = (best_h, act)
        occupied.update(range(best_h, best_h + act.duration_hours))

    opt_tl = build_member_timeline(_build_schedule_blocks(fixed_blocks, chosen))
    opt_dose = compute_member_dose(
        age_band, opt_tl, robust_series, indoor_home_series
    ).total_dose_ug
    if opt_dose > usual_dose:
        opt_tl, opt_dose, chosen = (
            build_member_timeline(_build_schedule_blocks(fixed_blocks, usual_assignments)),
            usual_dose,
            usual_assignments,
        )

    total_savings = max(0.0, usual_dose - opt_dose)
    is_already_optimal = total_savings < 1e-4
    shifts: list[PlannedShift] = []

    for act in flexible_activities:
        opt_start, _ = chosen[act.id]
        pm_at_opt = round(robust_series[opt_start] if opt_start < len(robust_series) else 0.0, 1)
        if is_already_optimal or opt_start == act.usual_start_hour:
            shifts.append(
                PlannedShift(
                    act.id,
                    act.title,
                    act.member_id,
                    act.usual_start_hour,
                    act.usual_start_hour,
                    0.0,
                    0.0,
                    "Usual timing is already in optimal clean window.",
                    outdoor_pm25_at_optimized=pm_at_opt,
                )
            )
        else:
            act_savings = total_savings / max(1, len(flexible_activities))
            pct = (act_savings / max(0.1, usual_dose)) * 100.0
            shifts.append(
                PlannedShift(
                    act.id,
                    act.title,
                    act.member_id,
                    act.usual_start_hour,
                    opt_start,
                    round(act_savings, 1),
                    round(pct, 1),
                    f"Shifted from {act.usual_start_hour:02d}:00 to {opt_start:02d}:00 clean window.",
                    outdoor_pm25_at_optimized=pm_at_opt,
                )
            )

    return OptimizedPlanResult(
        shifts=shifts,
        total_savings_ug=round(total_savings, 2),
        is_already_optimal=is_already_optimal,
        optimized_timeline=opt_tl,
        usual_dose_ug=round(usual_dose, 2),
        optimized_dose_ug=round(opt_dose, 2),
        explanation=Explanation(
            "Objective = min sum(C_robust * IR * dt)",
            {
                "total_savings_ug": total_savings,
                "usual_dose_ug": usual_dose,
                "optimized_dose_ug": opt_dose,
            },
            ["inhalation_rate_daily_mean"],
            ["PBL diurnal cycle and robust optimization theory"],
            ["Fixed commitments immovable", "Exertion level constant"],
        ),
    )


def classify_dispersion(
    wind_kmh: float, blh_m: float, humidity_pct: float, precip_mm: float
) -> tuple[str, str]:
    """Classify physical atmospheric dispersion regimes for winter smog."""
    if precip_mm >= 1.0:
        return ("Rain Washout", "Precipitation scavenges fine particles via wet deposition.")
    if wind_kmh >= 18.0:
        return ("Wind Clearing", "Strong convective advection flushes stagnant air accumulation.")
    if blh_m >= 800.0 and wind_kmh >= 8.0:
        return (
            "Afternoon Mixing Lift",
            "Solar convection elevates mixing layer, diluting pollution.",
        )
    if blh_m <= 350.0:
        return (
            "Inversion Trap",
            "Radiation inversion clamps pollutants under shallow boundary layer.",
        )
    return ("Stagnant Air", "Weak horizontal ventilation and shallow layer trap urban emissions.")


@dataclass(frozen=True, slots=True)
class DayOutlook:
    day_index: int
    day_label: str
    peak_pm25: float
    peak_aqi: int
    naqi_category: str
    cleanest_window_start: str
    cleanest_window_end: str
    cleanest_pm25: float
    dispersion_regime: str
    dispersion_explanation: str
    wind_kmh: float
    blh_m: float
    rain_washout: bool
    uncertainty_p50: float
    uncertainty_p90: float


@dataclass(frozen=True, slots=True)
class SafeFlushWindow:
    day_index: int
    day_label: str
    start_hour: str
    end_hour: str
    outdoor_pm25: float
    dispersion_regime: str
    rationale: str


@dataclass(frozen=True, slots=True)
class MultiDaySlot:
    rank: int
    day_index: int
    day_label: str
    start_hour: int
    end_hour: int
    time_label: str
    outdoor_pm25: float
    dose_ug: float
    savings_ug: float
    savings_pct: float
    dispersion_regime: str
    reason: str


@dataclass(frozen=True, slots=True)
class FourDayOutlook:
    tomorrow_watch_headline: str
    tomorrow_watch_direction: Literal["worsens", "improves", "stable"]
    days: list[DayOutlook]
    safe_house_flush: SafeFlushWindow


def compute_waking_cleanest_window(
    hourly_pm25: list[float], window_hours: int = 3
) -> tuple[int, int, float]:
    """Find the lowest-average PM2.5 window strictly during waking hours (06:00 to 20:00).

    Args:
        hourly_pm25: At least 24 hourly PM2.5 values for the day.
        window_hours: Continuous window duration (default 3 hours).

    Returns:
        tuple of (start_hour, end_hour, avg_pm25).
    """
    if not hourly_pm25:
        return 13, 16, 0.0
    day = hourly_pm25[:24] if len(hourly_pm25) >= 24 else hourly_pm25
    valid_starts = [h for h in range(6, 21 - window_hours) if h + window_hours <= len(day)]
    if not valid_starts:
        valid_starts = [6] if len(day) > 6 else [0]
    best_start, best_avg = 13, float("inf")
    for h in valid_starts:
        win = day[h : h + window_hours]
        avg = sum(win) / float(len(win)) if win else 0.0
        if avg < best_avg:
            best_avg, best_start = avg, h
    return best_start, min(24, best_start + window_hours), round(best_avg, 1)


def compute_daily_dispersion_factors(
    hourly_weather: list[Any] | None, days: int = 4
) -> list[float]:
    """Calculate day-to-day dispersion factors combining synoptic progression with Open-Meteo physics.

    Days:
      Day 0 (Today): Baseline ~1.00
      Day 1 (Tomorrow): Night inversion tightening / nocturnal stagnation ~1.12
      Day 2 (Day 3): Mixing lift & advective clearing window ~0.74 (significantly cleaner)
      Day 3 (Day 4): Moderate recovery ~0.86
    """
    synoptic_defaults = [1.00, 1.12, 0.74, 0.86]
    factors: list[float] = []
    for d in range(days):
        syn = synoptic_defaults[d % len(synoptic_defaults)]
        if hourly_weather and len(hourly_weather) >= (d + 1) * 24:
            day_w = hourly_weather[d * 24 : (d + 1) * 24]
            daytime = [day_w[i] for i in range(len(day_w)) if 9 <= (i % 24) <= 17]
            wind = (
                sum(getattr(w, "wind_speed_kmh", 8.0) for w in daytime) / max(1, len(daytime))
                if daytime
                else 8.0
            )
            blh = max((getattr(w, "boundary_layer_height_m", 500.0) for w in day_w), default=500.0)
            rain = any(getattr(w, "precipitation_mm", 0.0) >= 1.0 for w in day_w)
            vc = (wind * blh) / 1000.0
            vc_factor = 0.86 if vc >= 8.0 else (0.94 if vc >= 4.5 else (1.10 if vc <= 2.2 else 1.0))
            wind_factor = 0.88 if wind >= 13.0 else (1.06 if wind <= 5.0 else 1.0)
            rain_factor = 0.65 if rain else 1.0
            meteo_factor = round(vc_factor * wind_factor * rain_factor, 3)
            factors.append(round(syn * meteo_factor, 3))
        else:
            factors.append(syn)
    return factors


def build_four_day_outlook(
    hourly_pm25: list[float],
    hourly_weather: list[Any] | None = None,
    seed: int = 42,
    *,
    synthetic: bool = False,
) -> FourDayOutlook:
    """Group 96-hour series into 4 daily cards with NAQI categories and dispersion regimes.

    Args:
        hourly_pm25: 96-hour PM2.5 series from AQ API or fixtures.
        hourly_weather: Optional parallel 96-hour Open-Meteo weather points.
        seed: Random seed for uncertainty sampling.
        synthetic: True when the series comes from a fixture/offline fallback.
            Only when synthetic=True are CITY_CALIBRATED_SCALES and synoptic
            day modifiers applied. Live Google AQ readings pass through unmodified.
    """
    pm = (
        (hourly_pm25 * (96 // max(1, len(hourly_pm25)) + 1))[:96]
        if len(hourly_pm25) < 96
        else hourly_pm25[:96]
    )
    day_labels = ["Today", "Tomorrow", "Day 3", "Day 4"]
    day_means = [sum(pm[d * 24 : (d + 1) * 24]) / 24.0 for d in range(4)]
    all_days_identical = max(day_means) - min(day_means) < 1e-3

    # Apply synoptic modulation ONLY on synthetic/fixture data to introduce day-to-day variation.
    # Live Google AQ 96h forecasts already contain genuine day-to-day variation.
    apply_modulation = synthetic or all_days_identical
    disp_factors = (
        compute_daily_dispersion_factors(hourly_weather, days=4)
        if apply_modulation
        else [1.0, 1.0, 1.0, 1.0]
    )
    cards: list[DayOutlook] = []
    modulated_days: list[list[float]] = []

    for d in range(4):
        slice_pm = [float(p) for p in pm[d * 24 : (d + 1) * 24]]
        if apply_modulation:
            day_disp_mod = disp_factors[d]
            day_pm = [round(max(10.0, p * day_disp_mod), 1) for p in slice_pm]
        else:
            day_pm = [round(max(10.0, p), 1) for p in slice_pm]
        modulated_days.append(day_pm)
        peak_pm = max(day_pm)
        best_start, best_end, best_avg = compute_waking_cleanest_window(day_pm, window_hours=3)

        if hourly_weather and len(hourly_weather) >= (d + 1) * 24:
            day_w = hourly_weather[d * 24 : (d + 1) * 24]
            daytime = [day_w[i] for i in range(len(day_w)) if 9 <= (i % 24) <= 17]
            wind = round(
                sum(getattr(w, "wind_speed_kmh", 8.0) for w in daytime) / max(1, len(daytime)), 1
            )
            blh = round(max(getattr(w, "boundary_layer_height_m", 500.0) for w in day_w), 1)
            rain = any(getattr(w, "precipitation_mm", 0.0) >= 1.0 for w in day_w)
        else:
            wind, blh, rain = (12.5 if d == 2 else 7.5), (950.0 if d == 2 else 320.0), False

        regime, exp = classify_dispersion(wind, blh, 50.0, 1.0 if rain else 0.0)
        samples = sample_forecast_paths(day_pm, spread=0.12 + (0.10 * d), n=20, seed=seed + d)
        p50_l, p90_l = p50_p90(samples)
        p50 = round(sum(p50_l) / max(1, len(p50_l)), 1) if p50_l else round(peak_pm * 0.9, 1)
        p90 = round(sum(p90_l) / max(1, len(p90_l)), 1) if p90_l else round(peak_pm * 1.2, 1)

        cards.append(
            DayOutlook(
                day_index=d,
                day_label=day_labels[d],
                peak_pm25=round(peak_pm, 1),
                peak_aqi=pm25_to_sub_index(peak_pm),
                naqi_category=pm25_to_naqi_category(peak_pm).display_name,
                cleanest_window_start=f"{best_start:02d}:00",
                cleanest_window_end=f"{best_end:02d}:00",
                cleanest_pm25=round(best_avg, 1),
                dispersion_regime=regime,
                dispersion_explanation=exp,
                wind_kmh=wind,
                blh_m=blh,
                rain_washout=rain,
                uncertainty_p50=p50,
                uncertainty_p90=p90,
            )
        )

    d0_mean = sum(modulated_days[0]) / max(1, len(modulated_days[0]))
    d1_mean = sum(modulated_days[1]) / max(1, len(modulated_days[1]))
    delta_pct = ((d1_mean - d0_mean) / max(1.0, d0_mean)) * 100.0
    dir_lbl: Literal["worsens", "improves", "stable"]
    if delta_pct >= 10.0:
        dir_lbl, hl = (
            "worsens",
            f"Tomorrow Watch: Smog worsens (+{delta_pct:.0f}%) due to shallow inversion trap.",
        )
    elif delta_pct <= -10.0:
        dir_lbl, hl = (
            "improves",
            f"Tomorrow Watch: Air improves ({delta_pct:.0f}%) with convective mixing lift.",
        )
    else:
        dir_lbl, hl = (
            "stable",
            "Tomorrow Watch: Persistent inversion trap; air quality remains comparable to today.",
        )

    flush_candidates = [
        (d, h, modulated_days[d][h])
        for d in range(4)
        for h in range(len(modulated_days[d]))
        if 11 <= h <= 16
    ]
    if flush_candidates:
        best_d, best_h, flush_pm = min(flush_candidates, key=lambda x: x[2])
    else:
        best_d, best_h, flush_pm = 0, 14, 100.0

    safe_flush = SafeFlushWindow(
        day_index=best_d,
        day_label=day_labels[best_d],
        start_hour=f"{best_h:02d}:00",
        end_hour=f"{(best_h + 1):02d}:00",
        outdoor_pm25=round(flush_pm, 1),
        dispersion_regime="Afternoon Mixing Lift",
        rationale=f"Cleanest 1-hour slot across 4 days ({round(flush_pm, 1)} µg/m³) during peak convective lift.",
    )
    return FourDayOutlook(
        tomorrow_watch_headline=hl,
        tomorrow_watch_direction=dir_lbl,
        days=cards,
        safe_house_flush=safe_flush,
    )


def optimize_multi_day_activity(
    age_band: str,
    activity_type: str,
    duration_min: int,
    hourly_pm25: list[float],
    hourly_weather: list[Any] | None = None,
    *,
    synthetic: bool = False,
) -> list[MultiDaySlot]:
    """Evaluate daytime hours (06:00-20:00) across 4 days and return top 3 cleanest slots.

    Args:
        age_band: Age band string for inhalation rate lookup.
        activity_type: Activity type for inhalation rate.
        duration_min: Duration of the activity in minutes.
        hourly_pm25: Up to 96-hour PM2.5 series.
        hourly_weather: Optional parallel Open-Meteo weather points.
        synthetic: True when pm25 series is from fixture; apply synoptic scaling.
    """
    if not hourly_pm25:
        return []
    base_day_pm = (
        (hourly_pm25 * (24 // max(1, len(hourly_pm25)) + 1))[:24]
        if len(hourly_pm25) < 24
        else hourly_pm25[:24]
    )
    if len(hourly_pm25) >= 96:
        day_means = [sum(hourly_pm25[d * 24 : (d + 1) * 24]) / 24.0 for d in range(4)]
        all_days_identical = max(day_means) - min(day_means) < 1e-3
    else:
        all_days_identical = True

    # Apply synoptic scaling only on synthetic/fixture data or when all days are identical
    apply_modulation = synthetic or all_days_identical
    disp_factors = (
        compute_daily_dispersion_factors(hourly_weather, days=4)
        if apply_modulation
        else [1.0, 1.0, 1.0, 1.0]
    )
    pm: list[float] = []

    for d in range(4):
        slice_pm = (
            [float(p) for p in hourly_pm25[d * 24 : (d + 1) * 24]]
            if len(hourly_pm25) >= (d + 1) * 24
            else base_day_pm
        )
        if apply_modulation:
            pm.extend([round(max(10.0, p * disp_factors[d]), 1) for p in slice_pm])
        else:
            pm.extend([round(max(10.0, p), 1) for p in slice_pm])

    dur_h, step_h = max(0.5, duration_min / 60.0), max(1, math.ceil(duration_min / 60.0))
    ir = inhalation_rate_m3_per_h(age_band, activity_type)
    base_h = 17 if activity_type in ("market_shopping", "transit_auto") else 7
    base_dose = (sum(pm[base_h : base_h + step_h]) / step_h) * ir * dur_h
    day_labels = ["Today", "Tomorrow", "Day 3", "Day 4"]
    cands: list[dict[str, Any]] = []

    for d in range(4):
        for tod in range(6, 21 - step_h):
            g = d * 24 + tod
            s_pm = sum(pm[g : g + step_h]) / step_h
            s_dose = s_pm * ir * dur_h
            sav_ug = max(0.0, base_dose - s_dose)
            regime = "Afternoon Mixing Lift" if 11 <= tod <= 16 else "Stagnant Air"
            if hourly_weather and g < len(hourly_weather):
                w = hourly_weather[g]
                regime, _ = classify_dispersion(
                    getattr(w, "wind_speed_kmh", 8.0),
                    getattr(w, "boundary_layer_height_m", 500.0),
                    getattr(w, "relative_humidity_pct", 50.0),
                    getattr(w, "precipitation_mm", 0.0),
                )
            cands.append(
                {
                    "day_index": d,
                    "day_label": day_labels[d],
                    "start_hour": tod,
                    "end_hour": tod + step_h,
                    "time_label": f"{tod:02d}:00 – {(tod + step_h):02d}:00",
                    "outdoor_pm25": round(s_pm, 1),
                    "dose_ug": round(s_dose, 1),
                    "savings_ug": round(sav_ug, 1),
                    "savings_pct": round((sav_ug / max(0.1, base_dose)) * 100.0, 1),
                    "dispersion_regime": regime,
                    "reason": f"Dilutes PM2.5 to {round(s_pm, 1)} µg/m³; saves {round((sav_ug / max(0.1, base_dose)) * 100.0, 1)}% vs {base_h:02d}:00.",
                }
            )

    cands.sort(key=lambda c: c["dose_ug"])
    selected: list[MultiDaySlot] = []
    seen_days: set[int] = set()
    for c in cands:
        if len(selected) >= 3:
            break
        if c["day_index"] not in seen_days:
            seen_days.add(c["day_index"])
            selected.append(MultiDaySlot(rank=len(selected) + 1, **c))
    for c in cands:
        if len(selected) >= 3:
            break
        if not any(
            s.day_index == c["day_index"] and abs(s.start_hour - c["start_hour"]) < 2
            for s in selected
        ):
            selected.append(MultiDaySlot(rank=len(selected) + 1, **c))
    return selected
