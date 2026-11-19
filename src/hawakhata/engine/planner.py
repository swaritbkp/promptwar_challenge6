"""Clean-Window Planner."""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.dose import (
    ScheduleBlock,
    TimelineSlot,
    build_member_timeline,
    compute_member_dose,
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
