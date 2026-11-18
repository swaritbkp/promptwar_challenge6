"""Activity emissions calculation module.

Computes personal and household emissions (kg CO2 and g PM2.5) for transport,
heating, power, and waste activities using Indian empirical emission factors
(ARAI vehicular factors, CEA CO2 baseline database, CPCB biomass inventories).
"""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class EmissionValue:
    """Emission estimate with central, low, and high uncertainty bounds.

    Attributes:
        central: Best-estimate emission value.
        low: Lower bound of emission uncertainty interval.
        high: Upper bound of emission uncertainty interval.
    """

    central: float
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class ActivityEmissionsResult:
    """Emissions footprint of a specific activity."""

    activity_id: str
    units: float
    kg_co2: EmissionValue
    g_pm25: EmissionValue
    explanation: Explanation


def activity_emissions(activity_id: str, units: float) -> ActivityEmissionsResult:
    """Calculate emissions for an activity with low/central/high uncertainty bounds."""
    if units < 0:
        raise ValueError(f"Units must be non-negative, got {units}")

    factor_const = get_constant("emission_factor")
    factor_values = factor_const.value
    factor_ranges = factor_const.range

    if not isinstance(factor_values, dict) or activity_id not in factor_values:
        raise KeyError(f"Unknown activity_id '{activity_id}' in emission factors")

    val = factor_values[activity_id]
    range_val = factor_ranges.get(activity_id, {}) if isinstance(factor_ranges, dict) else {}

    # Extract central values
    c_co2 = float(val.get("kg_co2", 0.0))
    c_pm = float(val.get("g_pm25", 0.0))

    # Extract bounds or fallback to central
    co2_range = range_val.get("kg_co2", [c_co2, c_co2])
    pm_range = range_val.get("g_pm25", [c_pm, c_pm])

    low_co2 = float(co2_range[0])
    high_co2 = float(co2_range[1])
    low_pm = float(pm_range[0])
    high_pm = float(pm_range[1])

    kg_co2_val = EmissionValue(
        central=round(units * c_co2, 4),
        low=round(units * low_co2, 4),
        high=round(units * high_co2, 4),
    )
    g_pm25_val = EmissionValue(
        central=round(units * c_pm, 4),
        low=round(units * low_pm, 4),
        high=round(units * high_pm, 4),
    )

    exp = Explanation(
        formula="Emission(kg CO2, g PM2.5) = Units * EmissionFactor(central, [low, high])",
        inputs={
            "activity_id": activity_id,
            "units": f"{units:.2f}",
            "kg_co2_central": f"{kg_co2_val.central:.4f} kg",
            "g_pm25_central": f"{g_pm25_val.central:.4f} g",
        },
        constants_used=["emission_factor"],
        sources=[factor_const.source or "ARAI, CEA, CPCB inventories"],
        assumptions=[
            "Emission factors represent typical Indian urban fleet and fuel mix averages",
            "Uncertainty interval reflects vehicle vintage and operating conditions",
        ],
    )

    return ActivityEmissionsResult(
        activity_id=activity_id,
        units=units,
        kg_co2=kg_co2_val,
        g_pm25=g_pm25_val,
        explanation=exp,
    )
