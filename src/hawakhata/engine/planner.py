"""Clean-Window Activity Planner — shifts flexible routines to cleanest forecast hours."""

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

HOURS_IN_DAY: int = 24
EPSILON_DOSE: float = 1e-4
DEFAULT_ROBUST_LAMBDA = 0.5


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
    fixed_blocks: list[ScheduleBlock],
    activity_slots: dict[str, tuple[int, FlexibleActivity]],
) -> list[ScheduleBlock]:
    blocks = list(fixed_blocks)
    for act_id, (start_h, act) in activity_slots.items():
        blocks.append(
            ScheduleBlock(
                start_hour=start_h,
                end_hour=start_h + act.duration_hours,
                micro_env=act.micro_env,
                activity=act.activity,
                label=act.title or act_id,
            )
        )
    return blocks


def _is_valid_slot(
    start_h: int, duration: int, occupied_hours: set[int], earliest: int, latest: int
) -> bool:
    if (
        start_h < earliest
        or (start_h + duration - 1) > latest
        or (start_h + duration) > HOURS_IN_DAY
    ):
        return False
    return not bool(occupied_hours.intersection(range(start_h, start_h + duration)))


def _find_best_slot_for_activity(
    act: FlexibleActivity,
    chosen_assignments: dict[str, tuple[int, FlexibleActivity]],
    occupied_hours: set[int],
    *,
    fixed_blocks: list[ScheduleBlock],
    age_band: str,
    robust_series: list[float],
    indoor_home_series: list[float] | None,
) -> int:
    best_hour = act.usual_start_hour
    best_cost = float("inf")

    for h in range(act.earliest_start_hour, act.latest_start_hour + 1):
        if not _is_valid_slot(
            h, act.duration_hours, occupied_hours, act.earliest_start_hour, act.latest_start_hour
        ):
            continue
        test_assignments = dict(chosen_assignments)
        test_assignments[act.id] = (h, act)
        test_blocks = _build_schedule_blocks(fixed_blocks, test_assignments)
        test_tl = build_member_timeline(test_blocks)
        cost = compute_member_dose(
            age_band, test_tl, robust_series, indoor_home_series
        ).total_dose_ug
        if cost < best_cost:
            best_cost = cost
            best_hour = h

    if _is_valid_slot(
        act.usual_start_hour,
        act.duration_hours,
        occupied_hours,
        act.earliest_start_hour,
        act.latest_start_hour,
    ):
        test_usual = dict(chosen_assignments)
        test_usual[act.id] = (act.usual_start_hour, act)
        u_tl = build_member_timeline(_build_schedule_blocks(fixed_blocks, test_usual))
        u_cost = compute_member_dose(
            age_band, u_tl, robust_series, indoor_home_series
        ).total_dose_ug
        if abs(u_cost - best_cost) < EPSILON_DOSE:
            return act.usual_start_hour

    return best_hour


def optimise_day_plan(
    age_band: str,
    fixed_blocks: list[ScheduleBlock],
    flexible_activities: list[FlexibleActivity],
    outdoor_pm25_series: list[float],
    *,
    indoor_home_series: list[float] | None = None,
    robust_lambda: float = DEFAULT_ROBUST_LAMBDA,
    uncertainty_spread: float = 0.25,
    seed: int = 42,
) -> OptimizedPlanResult:
    """Find schedule allocations that minimize expected dose under uncertainty."""
    if robust_lambda > 0.0 and uncertainty_spread > 0.0:
        paths = sample_forecast_paths(
            outdoor_pm25_series, spread=uncertainty_spread, n=30, seed=seed
        )
        p50, p90 = p50_p90(paths)
        robust_series = [
            p50[i] + robust_lambda * max(0.0, p90[i] - p50[i]) for i in range(len(p50))
        ]
    else:
        robust_series = list(outdoor_pm25_series)

    usual_assignments = {a.id: (a.usual_start_hour, a) for a in flexible_activities}
    usual_blocks = _build_schedule_blocks(fixed_blocks, usual_assignments)
    usual_tl = build_member_timeline(usual_blocks)
    usual_dose = compute_member_dose(
        age_band, usual_tl, robust_series, indoor_home_series
    ).total_dose_ug

    occupied: set[int] = set()
    for b in fixed_blocks:
        occupied.update(range(max(0, b.start_hour), min(HOURS_IN_DAY, b.end_hour)))

    sorted_activities = sorted(flexible_activities, key=lambda a: a.duration_hours, reverse=True)
    chosen: dict[str, tuple[int, FlexibleActivity]] = {}

    for act in sorted_activities:
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

    opt_blocks = _build_schedule_blocks(fixed_blocks, chosen)
    opt_tl = build_member_timeline(opt_blocks)
    opt_dose = compute_member_dose(
        age_band, opt_tl, robust_series, indoor_home_series
    ).total_dose_ug

    if opt_dose > usual_dose:
        opt_tl = usual_tl
        opt_dose = usual_dose
        chosen = usual_assignments

    total_savings = max(0.0, usual_dose - opt_dose)
    is_already_optimal = total_savings < EPSILON_DOSE
    shifts: list[PlannedShift] = []

    for act in flexible_activities:
        opt_start, _ = chosen[act.id]
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
                )
            )
        else:
            act_savings = total_savings / max(1, len(flexible_activities))
            pct = (act_savings / max(0.1, usual_dose)) * 100.0
            shift_expl = (
                f"Shifted from {act.usual_start_hour:02d}:00 smog peak "
                f"to {opt_start:02d}:00 clean window."
            )
            shifts.append(
                PlannedShift(
                    act.id,
                    act.title,
                    act.member_id,
                    act.usual_start_hour,
                    opt_start,
                    round(act_savings, 1),
                    round(pct, 1),
                    shift_expl,
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
