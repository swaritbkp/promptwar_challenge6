from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.engine.dose import ScheduleBlock
from hawakhata.engine.planner import (
    FlexibleActivity,
    _is_valid_slot,
    optimise_day_plan,
)


def test_optimise_day_plan_shifts_morning_walk_to_afternoon() -> None:
    outdoor = [200.0] * 24
    outdoor[7] = 320.0
    outdoor[8] = 300.0
    outdoor[14] = 70.0
    outdoor[15] = 65.0

    fixed = [
        ScheduleBlock(start_hour=9, end_hour=13, micro_env="indoor_other", activity="sedentary"),
    ]
    flex = [
        FlexibleActivity(
            id="walk_dadi",
            member_id="dadi",
            title="Dadi's walk",
            duration_hours=1,
            earliest_start_hour=6,
            latest_start_hour=19,
            micro_env="outdoor",
            activity="moderate",
            usual_start_hour=7,
        )
    ]

    res = optimise_day_plan(
        age_band="61_71",
        fixed_blocks=fixed,
        flexible_activities=flex,
        outdoor_pm25_series=outdoor,
        robust_lambda=0.5,
    )
    assert len(res.shifts) == 1
    shift = res.shifts[0]
    assert shift.usual_start_hour == 7
    assert shift.optimized_start_hour in (14, 15)
    assert res.total_savings_ug > 0
    assert res.optimized_dose_ug < res.usual_dose_ug
    assert res.is_already_optimal is False


def test_optimise_day_plan_already_optimal() -> None:
    outdoor = [200.0] * 24
    outdoor[14] = 40.0
    flex = [
        FlexibleActivity(
            id="walk_1",
            member_id="m1",
            title="Walk",
            duration_hours=1,
            earliest_start_hour=6,
            latest_start_hour=18,
            micro_env="outdoor",
            activity="moderate",
            usual_start_hour=14,
        )
    ]
    res = optimise_day_plan(
        age_band="31_41",
        fixed_blocks=[],
        flexible_activities=flex,
        outdoor_pm25_series=outdoor,
        uncertainty_spread=0.0,
    )
    assert res.is_already_optimal is True
    assert res.total_savings_ug == 0.0
    assert res.shifts[0].optimized_start_hour == 14


def test_optimise_day_plan_never_moves_fixed_blocks_or_overlaps() -> None:
    fixed = [
        ScheduleBlock(start_hour=14, end_hour=16, micro_env="indoor_other", activity="sedentary"),
    ]
    # Even if 14:00 is cleanest, fixed block occupies 14..16, so planner must not overlap
    outdoor = [150.0] * 24
    outdoor[14] = 20.0
    outdoor[15] = 20.0
    outdoor[16] = 40.0

    flex = [
        FlexibleActivity(
            id="errand",
            member_id="m1",
            title="Errands",
            duration_hours=1,
            earliest_start_hour=12,
            latest_start_hour=18,
            micro_env="outdoor",
            activity="light",
            usual_start_hour=12,
        )
    ]
    res = optimise_day_plan(
        age_band="31_41",
        fixed_blocks=fixed,
        flexible_activities=flex,
        outdoor_pm25_series=outdoor,
    )
    shift = res.shifts[0]
    # Must NOT overlap with fixed 14 or 15!
    assert shift.optimized_start_hour not in (14, 15)
    assert shift.optimized_start_hour == 16  # cleanest available non-overlapping hour


def test_is_valid_slot_helper() -> None:
    assert _is_valid_slot(5, 1, set(), 6, 10) is False  # before earliest
    assert _is_valid_slot(10, 2, set(), 6, 10) is False  # exceeds latest
    assert _is_valid_slot(23, 2, set(), 0, 23) is False  # exceeds 24h
    assert _is_valid_slot(7, 2, {8}, 6, 10) is False  # collides with occupied
    assert _is_valid_slot(7, 2, {12}, 6, 10) is True  # valid slot


@given(
    morning_peak=st.floats(min_value=200.0, max_value=450.0),
    afternoon_trough=st.floats(min_value=30.0, max_value=120.0),
)
@settings(max_examples=50, deadline=None)
def test_property_planner_dose_never_exceeds_usual(
    morning_peak: float, afternoon_trough: float
) -> None:
    outdoor = [180.0] * 24
    outdoor[7] = morning_peak
    outdoor[14] = afternoon_trough

    flex = [
        FlexibleActivity(
            id="walk",
            member_id="m",
            title="Walk",
            duration_hours=1,
            earliest_start_hour=6,
            latest_start_hour=20,
            micro_env="outdoor",
            activity="moderate",
            usual_start_hour=7,
        )
    ]
    res = optimise_day_plan("31_41", [], flex, outdoor)
    # Optimized dose must be <= usual dose by construction
    assert res.optimized_dose_ug <= res.usual_dose_ug + 1e-4
    assert res.total_savings_ug >= 0.0
