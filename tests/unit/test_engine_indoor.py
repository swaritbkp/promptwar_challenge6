from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.engine.indoor_model import (
    IndoorSourceEvent,
    simulate_indoor_pm25,
    steady_state_pm25,
)


def test_steady_state_calculation() -> None:
    # V = 40 m3, C_out = 100 ug/m3, windows closed (a=0.5), k=0.2, P=0.8, CADR=0, S=0
    # lambda = 0.5 + 0.2 = 0.7 /h
    # C_ss = (0.8 * 0.5 * 100) / 0.7 = 40 / 0.7 = 57.1428 ug/m3
    c_ss = steady_state_pm25(c_out_ug_m3=100.0, room_volume_m3=40.0)
    assert pytest.approx(c_ss, rel=1e-3) == 57.143


def test_exact_step_equals_analytic_solution() -> None:
    # Compare exponential stepping against analytical ODE: C(t) = C_ss + (C0 - C_ss)*exp(-lambda*t)
    v = 50.0
    c_out = 200.0
    c0 = 150.0
    res = simulate_indoor_pm25(
        room_volume_m3=v,
        outdoor_pm25_series=[c_out],
        start_c_ug_m3=c0,
    )
    # 1 hour step
    p, a, k = 0.8, 0.5, 0.2
    lam = a + k
    c_ss = (p * a * c_out) / lam
    analytic_1h = c_ss + (c0 - c_ss) * math.exp(-lam * 1.0)
    assert abs(res.hourly_pm25_ug_m3[0] - analytic_1h) < 1e-9


def test_sub_hour_source_event_averaged() -> None:
    # 20 min tadka in hour 1
    event = IndoorSourceEvent(kind="src_tadka", start_hour=1, minutes=20.0)
    outdoor = [100.0] * 5
    res = simulate_indoor_pm25(
        room_volume_m3=40.0,
        outdoor_pm25_series=outdoor,
        source_events=[event],
        start_c_ug_m3=50.0,
    )
    # Hour 1 should see a substantial PM2.5 spike compared to hour 0
    assert res.hourly_pm25_ug_m3[1] > res.hourly_pm25_ug_m3[0]


@given(
    cadr1=st.floats(min_value=0.0, max_value=200.0),
    cadr2=st.floats(min_value=201.0, max_value=500.0),
    c_out=st.floats(min_value=50.0, max_value=300.0),
)
@settings(max_examples=50, deadline=None)
def test_property_more_cadr_never_increases_indoor_pm25(
    cadr1: float, cadr2: float, c_out: float
) -> None:
    outdoor = [c_out] * 12
    res_lower = simulate_indoor_pm25(
        room_volume_m3=40.0,
        outdoor_pm25_series=outdoor,
        purifier_cadr_m3_per_h=cadr1,
        purifier_on_hours=set(range(12)),
    )
    res_higher = simulate_indoor_pm25(
        room_volume_m3=40.0,
        outdoor_pm25_series=outdoor,
        purifier_cadr_m3_per_h=cadr2,
        purifier_on_hours=set(range(12)),
    )
    for h in range(12):
        # Higher CADR must never increase concentration
        assert res_higher.hourly_pm25_ug_m3[h] <= res_lower.hourly_pm25_ug_m3[h] + 1e-6


@given(
    c_out=st.floats(min_value=10.0, max_value=400.0),
)
@settings(max_examples=50, deadline=None)
def test_property_adding_source_never_lowers_indoor_pm25(c_out: float) -> None:
    outdoor = [c_out] * 6
    res_clean = simulate_indoor_pm25(
        room_volume_m3=40.0,
        outdoor_pm25_series=outdoor,
        start_c_ug_m3=50.0,
    )
    res_smoke = simulate_indoor_pm25(
        room_volume_m3=40.0,
        outdoor_pm25_series=outdoor,
        source_events=[IndoorSourceEvent("src_incense_stick", start_hour=2, minutes=30.0)],
        start_c_ug_m3=50.0,
    )
    for h in range(6):
        assert res_smoke.hourly_pm25_ug_m3[h] >= res_clean.hourly_pm25_ug_m3[h] - 1e-6
