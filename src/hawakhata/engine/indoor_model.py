"""Single-zone indoor PM2.5 mass-balance model with exact exponential time-stepping."""

from __future__ import annotations

import math
from dataclasses import dataclass

from hawakhata.engine.constants import get_constant
from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class IndoorSourceEvent:
    """An indoor particulate emission event (cooking, agarbatti, coil, smoking)."""

    kind: str
    start_hour: int
    minutes: float = 60.0
    count: int = 1


@dataclass(frozen=True, slots=True)
class IndoorSimulationResult:
    """Outcome of 24-hour indoor PM2.5 mass-balance simulation."""

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
    """Calculate asymptotic indoor PM2.5 steady-state concentration for constant inputs."""
    p = float(get_constant("indoor_penetration_factor").value)
    k = float(get_constant("indoor_deposition_rate").value)
    a = float(
        get_constant("air_exchange_open").value
        if windows_open
        else get_constant("air_exchange_closed").value
    )
    v = max(1.0, room_volume_m3)
    loss = a + k + (max(0.0, purifier_cadr_m3_per_h) / v)
    gen = (p * a * max(0.0, c_out_ug_m3)) + (max(0.0, source_strength_ug_per_h) / v)
    return gen / loss


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
    """Simulate hour-by-hour indoor PM2.5 concentration using exact exponential stepping."""
    open_h = windows_open_hours or set()
    pur_h = purifier_on_hours or set()
    events = source_events or []
    v = max(1.0, room_volume_m3)
    p = float(get_constant("indoor_penetration_factor").value)
    k = float(get_constant("indoor_deposition_rate").value)
    a_closed = float(get_constant("air_exchange_closed").value)
    a_open = float(get_constant("air_exchange_open").value)
    source_rates = get_constant("indoor_source_emission_rate").value

    hourly_s: dict[int, float] = {}
    for ev in events:
        base = float(source_rates.get(ev.kind, 0.0))
        frac = min(1.0, max(0.0, ev.minutes / 60.0))
        hourly_s[ev.start_hour] = hourly_s.get(ev.start_hour, 0.0) + base * frac * max(1, ev.count)

    c_out_0 = outdoor_pm25_series[0] if outdoor_pm25_series else 100.0
    cur_c = (
        max(0.0, start_c_ug_m3)
        if start_c_ug_m3 is not None
        else steady_state_pm25(
            c_out_0,
            v,
            0 in open_h,
            purifier_cadr_m3_per_h if 0 in pur_h else 0.0,
            hourly_s.get(0, 0.0),
        )
    )

    results: list[float] = []
    for h, c_out in enumerate(outdoor_pm25_series):
        a = a_open if h in open_h else a_closed
        cadr = purifier_cadr_m3_per_h if h in pur_h else 0.0
        s = hourly_s.get(h, 0.0)
        lam = a + k + (cadr / v)
        c_ss = ((p * a * max(0.0, c_out)) + (s / v)) / lam
        c_next = max(0.0, c_ss + (cur_c - c_ss) * math.exp(-lam * 1.0))
        results.append(c_next)
        cur_c = c_next

    mean_pm = (sum(results) / max(1, len(results))) if results else 0.0
    peak_pm = max(results) if results else 0.0
    exp = Explanation(
        formula="C(t+1)=C_ss+(C(t)-C_ss)*exp(-lam*1h); lam=a+k+CADR/V; C_ss=(P*a*C_out+S/V)/lam",
        inputs={
            "room_volume_m3": f"{v:.1f} m3",
            "purifier_cadr": f"{purifier_cadr_m3_per_h:.0f} m3/h",
            "simulated_mean_pm25": f"{mean_pm:.1f} ug/m3",
        },
        constants_used=[
            "indoor_penetration_factor",
            "indoor_deposition_rate",
            "air_exchange_closed",
            "air_exchange_open",
            "indoor_source_emission_rate",
        ],
        sources=["Chen & Zhao (2011)", "Thatcher & Layton (1995)"],
        assumptions=["Well-mixed single-zone model", "Constant exchange and source rates per hour"],
    )
    return IndoorSimulationResult(
        hourly_pm25_ug_m3=results, mean_pm25_ug_m3=mean_pm, peak_pm25_ug_m3=peak_pm, explanation=exp
    )


@dataclass(frozen=True, slots=True)
class PlantRealityCheck:
    """Scientific comparison of indoor plant deposition vs HEPA air filtration."""

    plant_count: int
    plant_cadr_m3_per_h: float
    hepa_cadr_m3_per_h: float
    hepa_to_plant_ratio: float
    percent_removal_by_plants: float
    verdict: str
    care_tips: list[str]


def compare_plants_vs_hepa(
    room_volume_m3: float = 60.0,
    plant_count: int = 5,
    hepa_cadr_m3_per_h: float = 300.0,
) -> PlantRealityCheck:
    """Compute physical PM2.5 deposition rate for potted plants vs mechanical HEPA CADR."""
    v = max(1.0, room_volume_m3)
    n = max(0, plant_count)
    plant_cadr = round(n * 0.1, 2)
    hepa_cadr = max(0.0, hepa_cadr_m3_per_h)
    ratio = round(hepa_cadr / max(0.05, plant_cadr), 1) if plant_cadr > 0 else 0.0
    natural_loss = (0.2 + 0.5) * v
    pct = round((plant_cadr / max(0.1, natural_loss + hepa_cadr + plant_cadr)) * 100.0, 2)
    verdict = (
        f"{n} potted plants provide ~{plant_cadr:.1f} m³/h CADR ({pct}% of room clearance). A HEPA purifier is {ratio:.0f}× more powerful for winter smog."
        if n > 0
        else "No plants modeled. Mechanical HEPA provides primary particulate protection."
    )
    tips = [
        "Wipe leaf dust weekly with a moist cloth so stomata stay unobstructed.",
        "Avoid over-watering in sealed rooms: damp soil promotes fungal aerosols.",
        "Enjoy plants for biophilia, but never rely on them as smog filters.",
    ]
    return PlantRealityCheck(
        plant_count=n,
        plant_cadr_m3_per_h=plant_cadr,
        hepa_cadr_m3_per_h=hepa_cadr,
        hepa_to_plant_ratio=ratio,
        percent_removal_by_plants=pct,
        verdict=verdict,
        care_tips=tips,
    )
