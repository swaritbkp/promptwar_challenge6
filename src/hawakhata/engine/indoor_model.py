"""Single-zone indoor PM2.5 mass-balance model with exact exponential time-stepping.

Differential Equation:
    dC/dt = P * a * C_out - lambda * C + S / V
where:
    lambda = a + k + (CADR / V)

Exact analytical step over 1 hour:
    C_ss = (P * a * C_out + S / V) / lambda
    C(t + 1h) = C_ss + (C(t) - C_ss) * exp(-lambda * 1h)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class IndoorSourceEvent:
    """An indoor particulate emission event (cooking, agarbatti, coil, smoking).

    Attributes:
        kind: Identifier from constants.v1.json (e.g. 'src_frying', 'src_incense_stick').
        start_hour: Hour of the day when activity starts (0..23).
        minutes: Duration in minutes (1..60).
        count: Number of active units (e.g. 2 incense sticks).
    """

    kind: str
    start_hour: int
    minutes: float = 60.0
    count: int = 1


@dataclass(frozen=True, slots=True)
class IndoorSimulationResult:
    """Outcome of 24-hour indoor PM2.5 mass-balance simulation.

    Attributes:
        hourly_pm25_ug_m3: Hourly concentration time-series.
        mean_pm25_ug_m3: 24-hour time-weighted average PM2.5 concentration.
        peak_pm25_ug_m3: Maximum hourly indoor concentration observed.
        explanation: Provenance, formula, and parameter container.
    """

    hourly_pm25_ug_m3: list[float]
    mean_pm25_ug_m3: float
    peak_pm25_ug_m3: float
    explanation: Explanation


def steady_state_pm25(
    c_out_ug_m3: float,
    room_volume_m3: float,
    windows_open: bool = False,
    purifier_cadr_m3_per_h: float = 0.0,
    source_strength_ug_per_h: float = 0.0,
) -> float:
    """Calculate the asymptotic indoor PM2.5 steady-state concentration for constant inputs.

    Formula:
        C_ss = (P * a * C_out + S / V) / (a + k + CADR / V)

    Args:
        c_out_ug_m3: Ambient outdoor PM2.5 concentration in ug/m3.
        room_volume_m3: Room volume in cubic meters.
        windows_open: True if windows are open, False if closed.
        purifier_cadr_m3_per_h: Purifier clean air delivery rate (CADR) in m3/h.
        source_strength_ug_per_h: Total indoor emission rate in ug/h.

    Returns:
        Steady-state indoor concentration in ug/m3.
    """
    p = float(get_constant("indoor_penetration_factor").value)
    k = float(get_constant("indoor_deposition_rate").value)
    a = float(
        get_constant("air_exchange_open").value
        if windows_open
        else get_constant("air_exchange_closed").value
    )

    v = max(1.0, room_volume_m3)
    loss_rate = a + k + (max(0.0, purifier_cadr_m3_per_h) / v)
    generation_term = (p * a * max(0.0, c_out_ug_m3)) + (max(0.0, source_strength_ug_per_h) / v)
    return generation_term / loss_rate


def simulate_indoor_pm25(
    room_volume_m3: float,
    outdoor_pm25_series: list[float],
    *,
    windows_open_hours: set[int] | None = None,
    purifier_cadr_m3_per_h: float = 0.0,
    purifier_on_hours: set[int] | None = None,
    source_events: list[IndoorSourceEvent] | None = None,
    start_c_ug_m3: float | None = None,
) -> IndoorSimulationResult:
    """Simulate hour-by-hour indoor PM2.5 concentration using exact exponential stepping.

    Args:
        room_volume_m3: Room volume in m3.
        outdoor_pm25_series: Sequence of hourly outdoor PM2.5 concentrations (ug/m3).
        windows_open_hours: Set of hours (0..23) when windows are open.
        purifier_cadr_m3_per_h: CADR rating of portable air cleaner (m3/h).
        purifier_on_hours: Set of hours when the purifier is powered on.
        source_events: Optional list of indoor combustion/cooking events.
        start_c_ug_m3: Initial concentration at hour 0. If None, steady-state of hour 0 is used.

    Returns:
        IndoorSimulationResult containing hourly concentrations, mean, peak, and explanation.
    """
    open_hours = windows_open_hours or set()
    purifier_hours = purifier_on_hours or set()
    events = source_events or []

    v = max(1.0, room_volume_m3)
    p = float(get_constant("indoor_penetration_factor").value)
    k = float(get_constant("indoor_deposition_rate").value)
    a_closed = float(get_constant("air_exchange_closed").value)
    a_open = float(get_constant("air_exchange_open").value)
    source_rates = get_constant("indoor_source_emission_rate").value

    # Pre-aggregate hourly source emissions (ug/h)
    hourly_sources: dict[int, float] = {}
    for ev in events:
        base_rate = float(source_rates.get(ev.kind, 0.0))
        # Sub-hour averaging: S_hour = base_rate * (minutes / 60.0) * count
        fraction = min(1.0, max(0.0, ev.minutes / 60.0))
        hourly_sources[ev.start_hour] = (
            hourly_sources.get(ev.start_hour, 0.0) + base_rate * fraction * max(1, ev.count)
        )

    # Initial condition
    c_out_0 = outdoor_pm25_series[0] if outdoor_pm25_series else 100.0
    if start_c_ug_m3 is not None:
        current_c = max(0.0, start_c_ug_m3)
    else:
        current_c = steady_state_pm25(
            c_out_ug_m3=c_out_0,
            room_volume_m3=v,
            windows_open=0 in open_hours,
            purifier_cadr_m3_per_h=purifier_cadr_m3_per_h if 0 in purifier_hours else 0.0,
            source_strength_ug_per_h=hourly_sources.get(0, 0.0),
        )

    hourly_results: list[float] = []

    for h, c_out in enumerate(outdoor_pm25_series):
        is_open = h in open_hours
        a = a_open if is_open else a_closed
        cadr = purifier_cadr_m3_per_h if h in purifier_hours else 0.0
        s = hourly_sources.get(h, 0.0)

        lam = a + k + (cadr / v)
        c_ss = ((p * a * max(0.0, c_out)) + (s / v)) / lam

        # Exact exponential solution across dt = 1.0 hour
        c_next = c_ss + (current_c - c_ss) * math.exp(-lam * 1.0)
        c_next = max(0.0, c_next)

        hourly_results.append(c_next)
        current_c = c_next

    mean_pm25 = (sum(hourly_results) / max(1, len(hourly_results))) if hourly_results else 0.0
    peak_pm25 = max(hourly_results) if hourly_results else 0.0

    exp = Explanation(
        formula="C(t+1) = C_ss + (C(t) - C_ss)*exp(-lambda*1h) where "
        "lambda = a + k + CADR/V, C_ss = (P*a*C_out + S/V)/lambda",
        inputs={
            "room_volume_m3": f"{v:.1f} m3",
            "purifier_cadr": f"{purifier_cadr_m3_per_h:.0f} m3/h",
            "windows_open_count": f"{len(open_hours)} hours",
            "events_modeled": f"{len(events)} events",
            "simulated_mean_pm25": f"{mean_pm25:.1f} ug/m3",
        },
        constants_used=[
            "indoor_penetration_factor",
            "indoor_deposition_rate",
            "air_exchange_closed",
            "air_exchange_open",
            "indoor_source_emission_rate",
        ],
        sources=[
            "Chen & Zhao (2011) Atmospheric Environment review of indoor PM2.5 infiltration",
            "Thatcher & Layton (1995) PM2.5 deposition rates in residences",
        ],
        assumptions=[
            "Well-mixed single-zone atmospheric model",
            "Constant exchange and source rates during each 1-hour interval",
        ],
    )

    return IndoorSimulationResult(
        hourly_pm25_ug_m3=hourly_results,
        mean_pm25_ug_m3=mean_pm25,
        peak_pm25_ug_m3=peak_pm25,
        explanation=exp,
    )
