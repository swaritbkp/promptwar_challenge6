from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.engine.dose import ScheduleBlock
from hawakhata.engine.planner import FlexibleActivity, _is_valid_slot, optimise_day_plan


def test_optimise_day_plan_shifts_morning_walk_to_afternoon() -> None:
    outdoor = [200.0] * 24
    outdoor[7], outdoor[8], outdoor[14], outdoor[15] = 320.0, 300.0, 70.0, 65.0
    fixed = [
        ScheduleBlock(start_hour=9, end_hour=13, micro_env="indoor_other", activity="sedentary")
    ]
    flex = [
        FlexibleActivity("walk_dadi", "dadi", "Dadi's walk", 1, 6, 19, "outdoor", "moderate", 7)
    ]
    res = optimise_day_plan("61_71", fixed, flex, outdoor, robust_lambda=0.5)
    assert len(res.shifts) == 1 and res.shifts[0].optimized_start_hour in (14, 15)
    assert res.total_savings_ug > 0 and res.optimized_dose_ug < res.usual_dose_ug


def test_optimise_day_plan_already_optimal() -> None:
    outdoor = [200.0] * 24
    outdoor[14] = 40.0
    flex = [FlexibleActivity("walk_1", "m1", "Walk", 1, 6, 18, "outdoor", "moderate", 14)]
    res = optimise_day_plan("31_41", [], flex, outdoor, uncertainty_spread=0.0)
    assert res.is_already_optimal is True and res.shifts[0].optimized_start_hour == 14


def test_optimise_day_plan_never_moves_fixed_blocks_or_overlaps() -> None:
    fixed = [
        ScheduleBlock(start_hour=14, end_hour=16, micro_env="indoor_other", activity="sedentary")
    ]
    outdoor = [150.0] * 24
    outdoor[14], outdoor[15], outdoor[16] = 20.0, 20.0, 40.0
    flex = [FlexibleActivity("errand", "m1", "Errands", 1, 12, 18, "outdoor", "light", 12)]
    res = optimise_day_plan("31_41", fixed, flex, outdoor)
    assert res.shifts[0].optimized_start_hour == 16


def test_is_valid_slot_helper() -> None:
    assert _is_valid_slot(5, 1, set(), 6, 10) is False
    assert _is_valid_slot(10, 2, set(), 6, 10) is False
    assert _is_valid_slot(23, 2, set(), 0, 23) is False
    assert _is_valid_slot(7, 2, {8}, 6, 10) is False
    assert _is_valid_slot(7, 2, {12}, 6, 10) is True


@given(
    morning_peak=st.floats(min_value=200.0, max_value=450.0),
    afternoon_trough=st.floats(min_value=30.0, max_value=120.0),
)
@settings(max_examples=30, deadline=None)
def test_property_planner_dose_never_exceeds_usual(
    morning_peak: float, afternoon_trough: float
) -> None:
    outdoor = [180.0] * 24
    outdoor[7], outdoor[14] = morning_peak, afternoon_trough
    flex = [FlexibleActivity("walk", "m", "Walk", 1, 6, 20, "outdoor", "moderate", 7)]
    res = optimise_day_plan("31_41", [], flex, outdoor)
    assert res.optimized_dose_ug <= res.usual_dose_ug + 1e-4 and res.total_savings_ug >= 0.0
