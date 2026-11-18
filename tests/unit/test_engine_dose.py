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
    ir_sed = inhalation_rate_m3_per_h("31_41", "sedentary")
    assert pytest.approx(ir_sed, rel=1e-3) == 0.5333

    ir_vig = inhalation_rate_m3_per_h("31_41", "vigorous")
    assert pytest.approx(ir_vig, rel=1e-3) == 3.0


def test_build_member_timeline_defaults() -> None:
    slots = build_member_timeline()
    assert len(slots) == 24
    for h in [22, 23, 0, 1, 2, 3, 4, 5]:
        assert slots[h].activity == "sleep" and slots[h].micro_env == "indoor_home"
    for h in [6, 12, 17, 21]:
        assert slots[h].activity == "sedentary" and slots[h].micro_env == "indoor_home"


def test_build_member_timeline_with_blocks() -> None:
    blocks = [
        ScheduleBlock(8, 10, "transit_car", "sedentary", "Car commute"),
        ScheduleBlock(17, 18, "outdoor", "moderate", "Evening walk"),
    ]
    slots = build_member_timeline(blocks)
    assert slots[8].micro_env == "transit_car" and slots[9].micro_env == "transit_car"
    assert slots[10].micro_env == "indoor_home" and slots[17].micro_env == "outdoor"


def test_compute_member_dose_branches() -> None:
    blocks = [
        ScheduleBlock(0, 8, "indoor_home", "sleep"),
        ScheduleBlock(8, 9, "transit_metro", "sedentary"),
        ScheduleBlock(9, 17, "indoor_other", "sedentary"),
        ScheduleBlock(17, 18, "transit_two_wheeler", "light"),
        ScheduleBlock(18, 19, "outdoor", "light"),
        ScheduleBlock(19, 24, "indoor_home", "sedentary"),
    ]
    timeline = build_member_timeline(blocks)
    res = compute_member_dose("6_11", timeline, [200.0] * 24, [50.0] * 24)
    assert res.total_dose_ug > 0
    assert res.hourly_concentrations_ug_m3[0] == 50.0
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
