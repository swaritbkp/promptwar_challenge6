from __future__ import annotations

import pytest

from hawakhata.engine.emissions import ActivityEmissionsResult, activity_emissions


def test_activity_emissions_car_petrol() -> None:
    res = activity_emissions("car_petrol_per_km", 20.0)
    assert (
        isinstance(res, ActivityEmissionsResult)
        and res.activity_id == "car_petrol_per_km"
        and res.units == 20.0
    )
    assert res.kg_co2.central == pytest.approx(
        3.2, rel=1e-3
    ) and res.g_pm25.central == pytest.approx(0.6, rel=1e-3)
    assert "ARAI" in res.explanation.sources[0]


def test_activity_emissions_angithi_coal() -> None:
    res = activity_emissions("angithi_coal_per_hour", 3.0)
    assert res.kg_co2.central == pytest.approx(
        4.5, rel=1e-3
    ) and res.g_pm25.central == pytest.approx(13.5, rel=1e-3)


def test_activity_emissions_unknown_activity_raises() -> None:
    with pytest.raises(KeyError, match="Unknown activity_id"):
        activity_emissions("space_rocket_launch", 1.0)


def test_activity_emissions_negative_units_raises() -> None:
    with pytest.raises(ValueError, match="Units must be non-negative"):
        activity_emissions("car_petrol_per_km", -5.0)
