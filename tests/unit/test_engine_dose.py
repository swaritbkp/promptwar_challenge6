from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.engine.dose import (
    ScheduleBlock,
    build_member_timeline,
    compute_member_dose,
    inhalation_rate_m3_per_h,
)


def test_inhalation_rate_calculation() -> None:
    # 31_41 mean daily is 16.0 m3/day -> hourly mean = 16.0/24 = 0.6667
    # sedentary mult is 0.8 -> 0.6667 * 0.8 = 0.5333
    ir_sed = inhalation_rate_m3_per_h("31_41", "sedentary")
    assert pytest.approx(ir_sed, rel=1e-3) == 0.5333

    # vigorous mult is 4.5 -> 0.6667 * 4.5 = 3.0
    ir_vig = inhalation_rate_m3_per_h("31_41", "vigorous")
    assert pytest.approx(ir_vig, rel=1e-3) == 3.0


def test_build_member_timeline_defaults() -> None:
    slots = build_member_timeline()
    assert len(slots) == 24
    # Check sleep hours
    for h in [22, 23, 0, 1, 2, 3, 4, 5]:
        assert slots[h].activity == "sleep"
        assert slots[h].micro_env == "indoor_home"
    # Check daytime default
    for h in [6, 12, 17, 21]:
        assert slots[h].activity == "sedentary"
        assert slots[h].micro_env == "indoor_home"


def test_build_member_timeline_with_blocks() -> None:
    blocks = [
        ScheduleBlock(
            start_hour=8,
            end_hour=10,
            micro_env="transit_car",
            activity="sedentary",
            label="Car commute",
        ),
        ScheduleBlock(
            start_hour=17,
            end_hour=18,
            micro_env="outdoor",
            activity="moderate",
            label="Evening walk",
        ),
    ]
    slots = build_member_timeline(blocks)
    assert slots[8].micro_env == "transit_car"
    assert slots[9].micro_env == "transit_car"
    assert slots[10].micro_env == "indoor_home"
    assert slots[17].micro_env == "outdoor"
    assert slots[17].activity == "moderate"


def test_compute_member_dose_branches() -> None:
    # Test indoor_home_series provided, indoor_other, and transit modes
    blocks = [
        ScheduleBlock(start_hour=0, end_hour=8, micro_env="indoor_home", activity="sleep"),
        ScheduleBlock(start_hour=8, end_hour=9, micro_env="transit_metro", activity="sedentary"),
        ScheduleBlock(start_hour=9, end_hour=17, micro_env="indoor_other", activity="sedentary"),
        ScheduleBlock(start_hour=17, end_hour=18, micro_env="transit_two_wheeler", activity="light"),
        ScheduleBlock(start_hour=18, end_hour=19, micro_env="outdoor", activity="light"),
        ScheduleBlock(start_hour=19, end_hour=24, micro_env="indoor_home", activity="sedentary"),
    ]
    timeline = build_member_timeline(blocks)
    outdoor = [200.0] * 24
    indoor = [50.0] * 24

    res = compute_member_dose(
        age_band="6_11",
        timeline=timeline,
        outdoor_pm25_series=outdoor,
        indoor_home_series=indoor,
    )
    assert res.total_dose_ug > 0
    # For hours 0..8, concentration should match indoor (50.0)
    assert res.hourly_concentrations_ug_m3[0] == 50.0
    # For hour 9, indoor_other should be 200 * 0.6 = 120.0
    assert res.hourly_concentrations_ug_m3[9] == 120.0


def test_compute_member_dose_zero_pollution() -> None:
    timeline = build_member_timeline()
    res = compute_member_dose("31_41", timeline, [0.0] * 24)
    assert res.total_dose_ug == 0.0
    assert all(d == 0.0 for d in res.hourly_doses_ug)


@given(
    scale=st.floats(min_value=0.1, max_value=5.0),
    base_conc=st.floats(min_value=1.0, max_value=500.0),
)
@settings(max_examples=50, deadline=None)
def test_property_dose_linear_in_concentration(scale: float, base_conc: float) -> None:
    timeline = build_member_timeline()
    series1 = [base_conc] * 24
    series2 = [base_conc * scale] * 24

    res1 = compute_member_dose(age_band="31_41", timeline=timeline, outdoor_pm25_series=series1)
    res2 = compute_member_dose(age_band="31_41", timeline=timeline, outdoor_pm25_series=series2)

    assert res1.total_dose_ug >= 0
    assert res2.total_dose_ug >= 0
    assert pytest.approx(res2.total_dose_ug, rel=1e-3) == res1.total_dose_ug * scale
