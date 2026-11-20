from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.engine.swaps import (
    CommunityImpactResult,
    SwapImpactResult,
    _compute_transit_delta_breathe,
    evaluate_swap,
    get_available_swaps,
    scale_to_community,
)


def test_get_available_swaps() -> None:
    cat = get_available_swaps()
    ids = [s["id"] for s in cat]
    assert len(cat) >= 6 and "commute_car_to_metro" in ids and "heating_angithi_to_electric" in ids


def test_evaluate_swap_commute_car_to_metro() -> None:
    res = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    assert isinstance(res, SwapImpactResult) and res.swap_id == "commute_car_to_metro"
    assert res.delta_emit_daily.kg_co2 < 0 and res.delta_emit_daily.g_pm25 < 0
    assert res.delta_emit_weekly.kg_co2 == pytest.approx(res.delta_emit_daily.kg_co2 * 5, rel=1e-4)

    # UI card parity: 15 km daily saves 2.1 kg CO2 and 15 ug PM2.5 inhaled
    r_ui = evaluate_swap("commute_car_to_metro", units_per_day=15.0, days_per_week=5)
    assert round(abs(r_ui.delta_emit_daily.kg_co2), 1) == 2.1
    assert round(abs(r_ui.delta_breathe_daily_ug), 0) == 15.0


def test_evaluate_swap_leaves_burning_to_compost() -> None:
    res = evaluate_swap("leaves_burning_to_compost", units_per_day=5.0, days_per_week=1)
    assert res.delta_emit_daily.g_pm25 < 0 and res.delta_emit_daily.kg_co2 < 0

    # UI card parity: 2 kg leaves daily saves 2.5 kg CO2 and avoids 24 g PM2.5 smoke
    r_ui = evaluate_swap("leaves_burning_to_compost", units_per_day=2.0, days_per_week=1)
    assert round(abs(r_ui.delta_emit_daily.kg_co2), 1) == 2.5
    assert round(abs(r_ui.delta_emit_daily.g_pm25), 0) == 24.0


def test_scale_to_community_zero_and_linear() -> None:
    swap_res = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    c0 = scale_to_community(swap_res, households=1000, participation_rate=0.0)
    assert isinstance(c0, CommunityImpactResult) and c0.community_delta_co2_kg_monthly == 0.0
    c1 = scale_to_community(swap_res, households=100, participation_rate=0.5)
    c2 = scale_to_community(swap_res, households=200, participation_rate=0.5)
    assert c2.community_delta_co2_kg_monthly == pytest.approx(
        c1.community_delta_co2_kg_monthly * 2, rel=1e-4
    )


def test_unknown_and_invalid_swaps_raises() -> None:
    with pytest.raises(KeyError):
        evaluate_swap("unknown_swap", units_per_day=10.0)
    with pytest.raises(ValueError, match="units_per_day"):
        evaluate_swap("commute_car_to_metro", units_per_day=-2.0)
    with pytest.raises(ValueError, match="days_per_week"):
        evaluate_swap("commute_car_to_metro", units_per_day=10.0, days_per_week=0)


def test_evaluate_swap_various_branches() -> None:
    r_two = evaluate_swap("commute_two_wheeler_to_metro", units_per_day=15.0, days_per_week=6)
    assert r_two.delta_emit_daily.kg_co2 < 0 and r_two.delta_breathe_daily_ug < 0
    r_heat = evaluate_swap("heating_angithi_to_electric", units_per_day=4.0, days_per_week=7)
    assert r_heat.delta_emit_daily.g_pm25 < 0
    assert round(abs(r_heat.delta_emit_daily.kg_co2), 1) == 0.2
    assert round(abs(r_heat.delta_emit_daily.g_pm25), 0) == 18.0
    r_inc = evaluate_swap("no_incense_on_severe_days", units_per_day=1.0)
    assert r_inc.delta_emit_daily.kg_co2 == 0.0 and r_inc.delta_emit_daily.g_pm25 == 0.0


def test_compute_transit_delta_breathe_helpers() -> None:
    tb = _compute_transit_delta_breathe
    assert tb("car_petrol_per_km", "bus_per_passenger_km", 200.0, "31_41", 1.0) > 0
    assert tb("car", "metro", 100.0, "unknown_age", 1.0) < 0


def test_evaluate_urban_indian_daily_habits_and_rwa_impact() -> None:
    # Kitchen chimney / exhaust during tadka
    r_chimney = evaluate_swap("kitchen_chimney_tadka", units_per_day=1.0)
    assert r_chimney.delta_breathe_daily_ug == -45.0
    assert r_chimney.delta_emit_daily.kg_co2 == 0.0

    # Skip coils and incense
    r_coils = evaluate_swap("skip_coils_and_incense", units_per_day=1.0)
    assert r_coils.delta_breathe_daily_ug == -60.0

    # Wet mopping vs dry jhadu
    r_mop = evaluate_swap("wet_mopping_vs_jhadu", units_per_day=1.0)
    assert r_mop.delta_breathe_daily_ug == -18.0

    # Car AC recirculation + combine errands / WFH
    r_car = evaluate_swap("car_recirc_wfh_errands", units_per_day=15.0)
    assert r_car.delta_emit_daily.kg_co2 < 0
    assert r_car.delta_breathe_daily_ug < 0

    # RWA guard heaters & composting
    r_guard = evaluate_swap("rwa_guard_heaters", units_per_day=4.0)
    assert r_guard.delta_emit_daily.g_pm25 < 0
    r_comp = evaluate_swap("rwa_leaf_composting", units_per_day=2.0)
    assert r_comp.delta_emit_daily.g_pm25 < 0
    assert r_comp.delta_emit_daily.kg_co2 < 0

    # RWA scaling across society flats (120 flats)
    c_rwa = scale_to_community(r_comp, households=120, participation_rate=1.0)
    assert c_rwa.community_delta_pm25_g_monthly < -1000.0


def test_scale_to_community_validation_errors() -> None:
    sr = evaluate_swap("commute_car_to_metro", units_per_day=10.0)
    with pytest.raises(ValueError):
        scale_to_community(sr, households=-5, participation_rate=0.5)
    with pytest.raises(ValueError):
        scale_to_community(sr, households=100, participation_rate=-0.1)


@given(
    households=st.integers(min_value=1, max_value=5000),
    participation=st.floats(min_value=0.0, max_value=1.0),
    units=st.floats(min_value=1.0, max_value=50.0),
)
@settings(max_examples=25, deadline=None)
def test_property_community_scaling_monotonic_and_zero_at_zero(
    households: int, participation: float, units: float
) -> None:
    sr = evaluate_swap("commute_car_to_metro", units_per_day=units, days_per_week=5)
    comm = scale_to_community(sr, households=households, participation_rate=participation)
    assert comm.community_delta_co2_kg_monthly <= 0.0
    if participation == 0.0:
        assert comm.community_delta_co2_kg_monthly == 0.0
