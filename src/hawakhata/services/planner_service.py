"""Planner service orchestrating clean-window activity schedule optimization."""

from __future__ import annotations

from hawakhata.api.schemas import FamilyProfileInput, FlexibleActivityInput
from hawakhata.core.errors import NotFoundError
from hawakhata.engine.dose import ScheduleBlock
from hawakhata.engine.indoor_model import IndoorSourceEvent, simulate_indoor_pm25
from hawakhata.engine.planner import FlexibleActivity, OptimizedPlanResult, optimise_day_plan


def compute_optimized_plan(
    profile: FamilyProfileInput,
    member_id: str,
    flexible_activities: list[FlexibleActivityInput],
    outdoor_pm25_series: list[float],
    *,
    robust_lambda: float = 0.5,
) -> OptimizedPlanResult:
    """Find schedule allocations that minimize personal particulate exposure."""
    target_member = next((m for m in profile.members if m.id == member_id), None)
    if target_member is None:
        raise NotFoundError(f"Member with id '{member_id}' was not found in profile")

    indoor_home_series: list[float] | None = None
    if profile.rooms:
        r = profile.rooms[0]
        events = [
            IndoorSourceEvent(s.kind, s.start_hour, s.minutes, s.count) for s in profile.sources
        ]
        sim = simulate_indoor_pm25(
            room_volume_m3=r.volume_m3,
            outdoor_pm25_series=outdoor_pm25_series,
            windows_open_hours=set(r.windows_open_hours),
            purifier_cadr_m3_per_h=r.purifier_cadr_m3_per_h,
            purifier_on_hours=set(r.purifier_on_hours),
            source_events=events,
        )
        indoor_home_series = sim.hourly_pm25_ug_m3

    fixed = [
        ScheduleBlock(b.start_hour, b.end_hour, b.micro_env, b.activity, b.label or b.activity)
        for b in target_member.schedule_blocks
    ]
    flex = [
        FlexibleActivity(
            fa.id,
            fa.member_id,
            fa.title,
            fa.duration_hours,
            fa.earliest_start_hour,
            fa.latest_start_hour,
            fa.micro_env,
            fa.activity,
            fa.usual_start_hour,
        )
        for fa in flexible_activities
    ]
    return optimise_day_plan(
        age_band=target_member.age_band,
        fixed_blocks=fixed,
        flexible_activities=flex,
        outdoor_pm25_series=outdoor_pm25_series,
        indoor_home_series=indoor_home_series,
        robust_lambda=robust_lambda,
    )
