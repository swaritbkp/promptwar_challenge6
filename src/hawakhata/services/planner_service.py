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

    # 1. Simulate indoor baseline if rooms exist
    indoor_home_series: list[float] | None = None
    if profile.rooms:
        primary_room = profile.rooms[0]
        events = [
            IndoorSourceEvent(
                kind=s.kind,
                start_hour=s.start_hour,
                minutes=s.minutes,
                count=s.count,
            )
            for s in profile.sources
        ]
        indoor_sim = simulate_indoor_pm25(
            room_volume_m3=primary_room.volume_m3,
            outdoor_pm25_series=outdoor_pm25_series,
            windows_open_hours=set(primary_room.windows_open_hours),
            purifier_cadr_m3_per_h=primary_room.purifier_cadr_m3_per_h,
            purifier_on_hours=set(primary_room.purifier_on_hours),
            source_events=events,
        )
        indoor_home_series = indoor_sim.hourly_pm25_ug_m3

    # 2. Convert member schedule blocks to engine ScheduleBlock objects
    fixed_blocks = [
        ScheduleBlock(
            start_hour=b.start_hour,
            end_hour=b.end_hour,
            micro_env=b.micro_env,
            activity=b.activity,
            label=b.label or b.activity,
        )
        for b in target_member.schedule_blocks
    ]

    # 3. Convert candidate flexible activities to engine FlexibleActivity objects
    flex_acts = [
        FlexibleActivity(
            id=fa.id,
            member_id=fa.member_id,
            title=fa.title,
            duration_hours=fa.duration_hours,
            earliest_start_hour=fa.earliest_start_hour,
            latest_start_hour=fa.latest_start_hour,
            micro_env=fa.micro_env,
            activity=fa.activity,
            usual_start_hour=fa.usual_start_hour,
        )
        for fa in flexible_activities
    ]

    return optimise_day_plan(
        age_band=target_member.age_band,
        fixed_blocks=fixed_blocks,
        flexible_activities=flex_acts,
        outdoor_pm25_series=outdoor_pm25_series,
        indoor_home_series=indoor_home_series,
        robust_lambda=robust_lambda,
    )
