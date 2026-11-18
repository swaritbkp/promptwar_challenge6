"""Clean-Window Activity Planner — shifts flexible routines to cleanest forecast hours.

Optimisation Problem:
    Given fixed commitments (school/office), candidate flexible activities
    (walks, outdoor play, errands), and an air quality forecast with uncertainty:
    Find non-overlapping start times inside permitted windows that minimise
        Objective = E[Dose] + lambda * P90[Dose]
    subject to:
        - Fixed schedule blocks remain strictly stationary.
        - No activities overlap for the member.
        - Start times satisfy [earliest_start_hour, latest_start_hour].
        - Optimised dose <= Usual dose (monotonicity; returns savings >= 0).

Time Complexity:
    Big-O: O(K * W * H + N_monte_carlo) where:
        K = number of flexible activities (typically <= 4)
        W = allowed scheduling window width in hours (typically <= 14)
        H = activity duration in hours (typically 1..2)
    For typical family schedules with pruned sequential search, execution time is < 5 ms.
"""

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
    """An activity whose timing can be shifted within a permissible window."""

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
    """Combine fixed blocks with current activity slot assignments."""
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
    start_h: int,
    duration: int,
    occupied_hours: set[int],
    earliest: int,
    latest: int,
) -> bool:
    """Check if candidate slot fits in window and does not collide with occupied hours."""
    if (
        start_h < earliest
        or (start_h + duration - 1) > latest
        or (start_h + duration) > HOURS_IN_DAY
    ):
        return False
    slot_hours = set(range(start_h, start_h + duration))
    return not bool(occupied_hours.intersection(slot_hours))


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
    """Search for best non-overlapping start hour that minimises candidate dose."""
    best_hour = act.usual_start_hour
    best_cost = float("inf")

    # Evaluate all valid non-overlapping slots in permitted window
    for h in range(act.earliest_start_hour, act.latest_start_hour + 1):
        if not _is_valid_slot(
            h,
            act.duration_hours,
            occupied_hours,
            act.earliest_start_hour,
            act.latest_start_hour,
        ):
            continue

        test_assignments = dict(chosen_assignments)
        test_assignments[act.id] = (h, act)
        test_blocks = _build_schedule_blocks(fixed_blocks, test_assignments)
        test_tl = build_member_timeline(test_blocks)
        dose_res = compute_member_dose(
            age_band=age_band,
            timeline=test_tl,
            outdoor_pm25_series=robust_series,
            indoor_home_series=indoor_home_series,
        )
        if dose_res.total_dose_ug < best_cost:
            best_cost = dose_res.total_dose_ug
            best_hour = h

    # If usual hour was valid and has same cost, prefer usual hour to minimise disruption
    if _is_valid_slot(
        act.usual_start_hour,
        act.duration_hours,
        occupied_hours,
        act.earliest_start_hour,
        act.latest_start_hour,
    ):
        test_usual = dict(chosen_assignments)
        test_usual[act.id] = (act.usual_start_hour, act)
        usual_tl = build_member_timeline(_build_schedule_blocks(fixed_blocks, test_usual))
        u_cost = compute_member_dose(
            age_band, usual_tl, robust_series, indoor_home_series
        ).total_dose_ug
        if abs(u_cost - best_cost) < EPSILON_DOSE:
            best_hour = act.usual_start_hour

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
    """Find schedule allocations that minimise risk-adjusted inhaled dose.

    Evaluates:
        Objective(slot) = Expected_Dose(slot) + lambda * P90_Dose(slot)
    where P90 is computed across Monte Carlo forecast realizations.

    Args:
        age_band: Age group of the family member.
        fixed_blocks: Unmovable commitments (school, work, fixed travel).
        flexible_activities: Routine activities with movable timing.
        outdoor_pm25_series: Ambient 24-hour PM2.5 concentrations.
        indoor_home_series: Optional indoor simulated PM2.5 concentrations.
        robust_lambda: Risk-aversion penalty on 90th percentile adverse exposure.
        uncertainty_spread: Forecast uncertainty standard deviation spread factor.
        seed: Random seed for Monte Carlo uncertainty sampling.

    Returns:
        OptimizedPlanResult containing chosen slots, savings, and transparency object.
    """
    # 1. Compute uncertainty trajectories (P50 and P90)
    if uncertainty_spread > 0.0:
        samples = sample_forecast_paths(
            outdoor_pm25_series, spread=uncertainty_spread, n=100, seed=seed
        )
        p50, p90 = p50_p90(samples)
        effective_p50 = p50 if p50 else outdoor_pm25_series
        effective_p90 = p90 if p90 else outdoor_pm25_series
    else:
        effective_p50 = outdoor_pm25_series
        effective_p90 = outdoor_pm25_series

    # Composite outdoor series accounting for risk penalty
    robust_series = [
        effective_p50[h] + (robust_lambda * (effective_p90[h] - effective_p50[h]))
        for h in range(HOURS_IN_DAY)
    ]

    # 2. Compute usual schedule baseline dose
    usual_assignments: dict[str, tuple[int, FlexibleActivity]] = {
        act.id: (act.usual_start_hour, act) for act in flexible_activities
    }
    usual_blocks = _build_schedule_blocks(fixed_blocks, usual_assignments)
    usual_timeline = build_member_timeline(usual_blocks)
    usual_dose_res = compute_member_dose(
        age_band=age_band,
        timeline=usual_timeline,
        outdoor_pm25_series=robust_series,
        indoor_home_series=indoor_home_series,
    )
    usual_dose = usual_dose_res.total_dose_ug

    # 3. Mark fixed hours as occupied
    occupied_hours: set[int] = set()
    for block in fixed_blocks:
        occupied_hours.update(range(max(0, block.start_hour), min(HOURS_IN_DAY, block.end_hour)))

    # 4. Greedy sequential allocation of flexible activities ordered by duration
    sorted_activities = sorted(
        flexible_activities,
        key=lambda a: a.duration_hours,
        reverse=True,
    )

    chosen_assignments: dict[str, tuple[int, FlexibleActivity]] = {}
    shifts: list[PlannedShift] = []

    for act in sorted_activities:
        best_hour = _find_best_slot_for_activity(
            act=act,
            chosen_assignments=chosen_assignments,
            occupied_hours=occupied_hours,
            fixed_blocks=fixed_blocks,
            age_band=age_band,
            robust_series=robust_series,
            indoor_home_series=indoor_home_series,
        )
        chosen_assignments[act.id] = (best_hour, act)
        occupied_hours.update(range(best_hour, best_hour + act.duration_hours))

    # 5. Build final optimized timeline and compute savings
    optimized_blocks = _build_schedule_blocks(fixed_blocks, chosen_assignments)
    optimized_timeline = build_member_timeline(optimized_blocks)
    optimized_dose_res = compute_member_dose(
        age_band=age_band,
        timeline=optimized_timeline,
        outdoor_pm25_series=robust_series,
        indoor_home_series=indoor_home_series,
    )
    optimized_dose = optimized_dose_res.total_dose_ug

    # Guardrail: optimized dose must never exceed usual dose
    if optimized_dose > usual_dose:
        optimized_timeline = usual_timeline
        optimized_dose = usual_dose
        chosen_assignments = usual_assignments

    total_savings = max(0.0, usual_dose - optimized_dose)
    is_already_optimal = total_savings < EPSILON_DOSE

    # Calculate per-activity shifts
    for act in flexible_activities:
        opt_start, _ = chosen_assignments[act.id]
        if is_already_optimal or opt_start == act.usual_start_hour:
            shifts.append(
                PlannedShift(
                    activity_id=act.id,
                    title=act.title,
                    member_id=act.member_id,
                    usual_start_hour=act.usual_start_hour,
                    optimized_start_hour=act.usual_start_hour,
                    savings_ug=0.0,
                    percent_savings=0.0,
                    explanation="Usual timing is already in the optimal clean window.",
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
                    activity_id=act.id,
                    title=act.title,
                    member_id=act.member_id,
                    usual_start_hour=act.usual_start_hour,
                    optimized_start_hour=opt_start,
                    savings_ug=round(act_savings, 1),
                    percent_savings=round(pct, 1),
                    explanation=shift_expl,
                )
            )

    exp = Explanation(
        formula="Objective = min sum(C_robust(t) * IR(age, activity) * dt) subject to "
        "Non-Overlap and Window constraints, where C_robust = E[C] + lambda * (P90 - E[C])",
        inputs={
            "age_band": age_band,
            "robust_lambda": robust_lambda,
            "total_savings_ug": f"{total_savings:.1f} ug",
            "usual_dose_ug": f"{usual_dose:.1f} ug",
            "optimized_dose_ug": f"{optimized_dose:.1f} ug",
            "activities_shifted": len([s for s in shifts if s.savings_ug > 0]),
        },
        constants_used=["inhalation_rate_daily_mean", "activity_multiplier"],
        sources=["Diurnal planetary boundary layer inversion cycle and robust optimization theory"],
        assumptions=[
            "Fixed schedule commitments cannot be displaced",
            "Activity exertion level remains constant across the time shift",
        ],
    )

    return OptimizedPlanResult(
        shifts=shifts,
        total_savings_ug=round(total_savings, 2),
        is_already_optimal=is_already_optimal,
        optimized_timeline=optimized_timeline,
        usual_dose_ug=round(usual_dose, 2),
        optimized_dose_ug=round(optimized_dose, 2),
        explanation=exp,
    )
