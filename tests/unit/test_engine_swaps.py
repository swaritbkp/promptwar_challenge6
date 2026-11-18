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
    catalogue = get_available_swaps()
    assert len(catalogue) >= 6
    ids = [s["id"] for s in catalogue]
    assert "commute_car_to_metro" in ids and "heating_angithi_to_electric" in ids


def test_evaluate_swap_commute_car_to_metro() -> None:
    res = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    assert isinstance(res, SwapImpactResult) and res.swap_id == "commute_car_to_metro"
    assert res.delta_emit_daily.kg_co2 < 0 and res.delta_emit_daily.g_pm25 < 0
    assert res.delta_emit_weekly.kg_co2 == pytest.approx(res.delta_emit_daily.kg_co2 * 5, rel=1e-4)
    assert res.delta_emit_monthly.kg_co2 == pytest.approx(
        res.delta_emit_weekly.kg_co2 * 4.33, rel=1e-4
    )


def test_evaluate_swap_leaves_burning_to_compost() -> None:
    res = evaluate_swap("leaves_burning_to_compost", units_per_day=5.0, days_per_week=1)
    assert res.delta_emit_daily.g_pm25 < 0 and res.delta_emit_daily.kg_co2 < 0


def test_scale_to_community_zero_participation() -> None:
    swap_res = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    comm = scale_to_community(swap_res, households=1000, participation_rate=0.0)
    assert isinstance(comm, CommunityImpactResult)
    assert comm.community_delta_co2_kg_monthly == 0.0 and comm.community_delta_pm25_g_monthly == 0.0


def test_scale_to_community_linear() -> None:
    swap_res = evaluate_swap("commute_car_to_metro", units_per_day=20.0, days_per_week=5)
    c1 = scale_to_community(swap_res, households=100, participation_rate=0.5)
    c2 = scale_to_community(swap_res, households=200, participation_rate=0.5)
    assert c2.community_delta_co2_kg_monthly == pytest.approx(
        c1.community_delta_co2_kg_monthly * 2, rel=1e-4
    )
    assert c2.community_delta_pm25_g_monthly == pytest.approx(
        c1.community_delta_pm25_g_monthly * 2, rel=1e-4
    )


def test_unknown_swap_raises() -> None:
    with pytest.raises(KeyError, match="Unknown swap_id"):
        evaluate_swap("unknown_swap", units_per_day=10.0)


def test_evaluate_swap_two_wheeler_to_metro() -> None:
    res = evaluate_swap("commute_two_wheeler_to_metro", units_per_day=15.0, days_per_week=6)
    assert res.delta_emit_daily.kg_co2 < 0 and res.delta_emit_daily.g_pm25 < 0
    assert res.delta_breathe_daily_ug < 0


def test_evaluate_swap_heating_angithi_to_electric() -> None:
    res = evaluate_swap("heating_angithi_to_electric", units_per_day=3.0, days_per_week=7)
    assert res.delta_emit_daily.g_pm25 < 0


def test_evaluate_swap_indoor_only_no_emissions_branch() -> None:
    res = evaluate_swap("no_incense_on_severe_days", units_per_day=1.0)
    assert res.delta_emit_daily.kg_co2 == 0.0 and res.delta_emit_daily.g_pm25 == 0.0


def test_compute_transit_delta_breathe_helpers() -> None:
    d_bus = _compute_transit_delta_breathe(
        "car_petrol_per_km", "bus_per_passenger_km", 200.0, "31_41", 1.0
    )
    assert d_bus > 0
    d_unknown = _compute_transit_delta_breathe("car", "metro", 100.0, "unknown_age", 1.0)
    assert d_unknown < 0
    with pytest.raises(ValueError, match="units_per_day must be non-negative"):
        evaluate_swap("commute_car_to_metro", units_per_day=-2.0)
    with pytest.raises(ValueError, match="days_per_week must be between 1 and 7"):
        evaluate_swap("commute_car_to_metro", units_per_day=10.0, days_per_week=0)
    with pytest.raises(ValueError, match="days_per_week must be between 1 and 7"):
        evaluate_swap("commute_car_to_metro", units_per_day=10.0, days_per_week=8)


def test_scale_to_community_validation_errors() -> None:
    swap_res = evaluate_swap("commute_car_to_metro", units_per_day=10.0)
    with pytest.raises(ValueError, match="households must be non-negative"):
        scale_to_community(swap_res, households=-5, participation_rate=0.5)
    with pytest.raises(ValueError, match=r"participation_rate must be between 0\.0 and 1\.0"):
        scale_to_community(swap_res, households=100, participation_rate=-0.1)
    with pytest.raises(ValueError, match=r"participation_rate must be between 0\.0 and 1\.0"):
        scale_to_community(swap_res, households=100, participation_rate=1.5)


@given(
    households=st.integers(min_value=1, max_value=5000),
    participation=st.floats(min_value=0.0, max_value=1.0),
    units=st.floats(min_value=1.0, max_value=50.0),
)
@settings(max_examples=40, deadline=None)
def test_property_community_scaling_monotonic_and_zero_at_zero(
    households: int, participation: float, units: float
) -> None:
    swap_res = evaluate_swap("commute_car_to_metro", units_per_day=units, days_per_week=5)
    comm = scale_to_community(swap_res, households=households, participation_rate=participation)
    assert comm.community_delta_co2_kg_monthly <= 0.0
    assert comm.community_delta_pm25_g_monthly <= 0.0
    if participation == 0.0:
        assert comm.community_delta_co2_kg_monthly == 0.0
        assert comm.community_delta_pm25_g_monthly == 0.0
