"""Indoor air quality hacks, purifier sizing heuristics, and natural ventilation timing.

Implements the clean-window ventilation test (C_out < C_in), AHAM AC-1 purifier
sizing (CADR >= V * target_ach), and ranked indoor particulate reduction interventions.
"""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.explain import Explanation
from hawakhata.engine.indoor_model import (
    IndoorSourceEvent,
    simulate_indoor_pm25,
)

MIN_MEANINGFUL_DELTA_UG_M3 = 0.1
DEFAULT_PURIFIER_ACH = 5.0


@dataclass(frozen=True, slots=True)
class VentilationRecommendation:
    """Airing advice identifying optimal hours for natural cross-ventilation.

    Attributes:
        recommended_hours: List of hours (0..23) when opening windows cleans indoor air.
        qualifying_count: Total hours in the forecast where outdoor PM2.5 < indoor PM2.5.
        reason: Human-facing guidance explaining why ventilation is or is not advised.
        explanation: Full calculation transparency container.
    """

    recommended_hours: list[int]
    qualifying_count: int
    reason: str
    explanation: Explanation


@dataclass(frozen=True, slots=True)
class PurifierRecommendation:
    """Portable HEPA air purifier sizing verdict.

    Attributes:
        required_cadr_m3_per_h: Minimum Clean Air Delivery Rate (m3/h) needed for 5 ACH.
        current_cadr_m3_per_h: User's owned purifier capacity.
        is_sufficient: True if owned CADR meets or exceeds requirement.
        deficit_m3_per_h: Deficit in m3/h if undersized.
        advice: Practical placement and usage guidance.
        explanation: Calculation provenance container.
    """

    required_cadr_m3_per_h: float
    current_cadr_m3_per_h: float
    is_sufficient: bool
    deficit_m3_per_h: float
    advice: str
    explanation: Explanation


@dataclass(frozen=True, slots=True)
class IndoorHack:
    """A ranked practical intervention reducing indoor particulate exposure.

    Attributes:
        id: Unique identifier for the hack.
        title: Short actionable summary.
        delta_pm25_ug_m3: Modeled reduction in daily mean indoor PM2.5 concentration.
        advice: Actionable steps for the family.
        explanation: Calculation transparency container.
    """

    id: str
    title: str
    delta_pm25_ug_m3: float
    advice: str
    explanation: Explanation


def recommend_ventilation_hours(
    outdoor_series: list[float],
    indoor_baseline_series: list[float],
    max_hours: int = 3,
) -> VentilationRecommendation:
    """Identify windows where airing the house measurably reduces indoor PM2.5.

    Condition:
        C_outdoor(t) < C_indoor(t)
    Sorted by:
        Lowest outdoor concentration first (cleanest ambient hours).

    Args:
        outdoor_series: 24-hour sequence of ambient PM2.5 concentrations in ug/m3.
        indoor_baseline_series: 24-hour sequence of unventilated indoor PM2.5 levels.
        max_hours: Maximum number of ventilation hours to recommend.

    Returns:
        VentilationRecommendation with recommended hours and reasoning.
    """
    qualifying: list[tuple[int, float]] = []
    num_hours = min(len(outdoor_series), len(indoor_baseline_series), 24)

    for h in range(num_hours):
        c_out = outdoor_series[h]
        c_in = indoor_baseline_series[h]
        if c_out < c_in:
            qualifying.append((h, c_out))

    qualifying.sort(key=lambda x: x[1])  # lowest outdoor PM2.5 first
    chosen_hours = [h for h, _ in qualifying[:max_hours]]

    if chosen_hours:
        formatted = ", ".join(f"{h:02d}:00" for h in sorted(chosen_hours))
        reason = (
            f"Outdoor air is cleaner than indoor air during {formatted}. "
            "Open windows during these cleanest hours to flush indoor particulates."
        )
    else:
        reason = (
            "Outdoor air is more polluted than indoor air throughout the day. "
            "Keep windows and exterior doors closed to prevent particulate infiltration."
        )

    exp = Explanation(
        formula="Airing qualifying condition: C_outdoor(h) < C_indoor(h), sorted by min(C_out)",
        inputs={
            "qualifying_count": len(qualifying),
            "max_hours_requested": max_hours,
            "chosen_hours": chosen_hours,
        },
        constants_used=["air_exchange_open", "air_exchange_closed"],
        sources=["US EPA / WHO indoor-outdoor air exchange mitigation guidance"],
        assumptions=["Cross-ventilation achieves 3.0 air changes per hour when windows open"],
    )

    return VentilationRecommendation(
        recommended_hours=chosen_hours,
        qualifying_count=len(qualifying),
        reason=reason,
        explanation=exp,
    )


def recommend_purifier_cadr(
    room_volume_m3: float,
    current_cadr_m3_per_h: float = 0.0,
    target_ach: float = DEFAULT_PURIFIER_ACH,
) -> PurifierRecommendation:
    """Evaluate whether an air purifier's CADR is adequate for the specified room volume.

    Formula:
        Required_CADR = Room_Volume * Target_ACH (default 5 ACH)

    Args:
        room_volume_m3: Volume of the target room in m3.
        current_cadr_m3_per_h: Stated clean air delivery rate of owned purifier (m3/h).
        target_ach: Desired air change rate per hour under severe smog.

    Returns:
        PurifierRecommendation with capacity sufficiency verdict.
    """
    v = max(1.0, room_volume_m3)
    required = v * target_ach
    deficit = max(0.0, required - current_cadr_m3_per_h)
    sufficient = current_cadr_m3_per_h >= required

    if sufficient:
        advice = (
            f"Your purifier ({current_cadr_m3_per_h:.0f} m³/h CADR) is sufficient for this "
            f"{v:.0f} m³ room. Run it continuously in the bedroom during sleeping hours."
        )
    else:
        advice = (
            f"This {v:.0f} m³ room needs at least {required:.0f} m³/h CADR for effective "
            f"filtration (deficit of {deficit:.0f} m³/h). Move purifier closer to bed or add CADR."
        )

    exp = Explanation(
        formula="Required_CADR = Room_Volume (m3) * Target_ACH (5/h)",
        inputs={
            "room_volume_m3": f"{v:.1f} m3",
            "current_cadr": f"{current_cadr_m3_per_h:.0f} m3/h",
            "target_ach": f"{target_ach:.1f} /h",
            "required_cadr": f"{required:.0f} m3/h",
        },
        constants_used=["purifier_target_ach"],
        sources=[
            "AHAM AC-1 method for measuring portable air cleaner performance",
            "US EPA Guide to Air Cleaners in the Home",
        ],
        assumptions=["5 effective air changes per hour for smoke/smog conditions"],
    )

    return PurifierRecommendation(
        required_cadr_m3_per_h=required,
        current_cadr_m3_per_h=current_cadr_m3_per_h,
        is_sufficient=sufficient,
        deficit_m3_per_h=deficit,
        advice=advice,
        explanation=exp,
    )


def _eval_hack(
    hack_id: str,
    title: str,
    advice: str,
    source_citation: str,
    formula: str,
    *,
    v: float,
    outdoor_series: list[float],
    windows_open_hours: set[int],
    purifier_cadr: float,
    purifier_hours: set[int],
    events: list[IndoorSourceEvent],
    base_mean: float,
) -> IndoorHack | None:
    """Evaluate a single hack and return an IndoorHack if savings exceed threshold."""
    sim = simulate_indoor_pm25(
        room_volume_m3=v,
        outdoor_pm25_series=outdoor_series,
        windows_open_hours=windows_open_hours,
        purifier_cadr_m3_per_h=purifier_cadr,
        purifier_on_hours=purifier_hours,
        source_events=events,
    )
    delta = base_mean - sim.mean_pm25_ug_m3
    if delta <= MIN_MEANINGFUL_DELTA_UG_M3:
        return None

    return IndoorHack(
        id=hack_id,
        title=title,
        delta_pm25_ug_m3=round(delta, 1),
        advice=advice,
        explanation=Explanation(
            formula=formula,
            inputs={"delta_pm25_ug_m3": f"{delta:.1f} ug/m3"},
            constants_used=["indoor_source_emission_rate"],
            sources=[source_citation],
            assumptions=["Model intervention applied across full 24-hour cycle"],
        ),
    )


def rank_indoor_hacks(
    room_volume_m3: float,
    outdoor_series: list[float],
    baseline_events: list[IndoorSourceEvent],
    *,
    purifier_cadr_m3_per_h: float = 0.0,
    purifier_on_hours: set[int] | None = None,
    windows_open_hours: set[int] | None = None,
) -> list[IndoorHack]:
    """Rank the top 5 indoor air quality interventions by modeled PM2.5 reduction.

    Args:
        room_volume_m3: Room volume in m3.
        outdoor_series: 24-hour outdoor concentration series.
        baseline_events: Current list of active combustion/cooking activities.
        purifier_cadr_m3_per_h: Current purifier CADR.
        purifier_on_hours: Current hours purifier is active.
        windows_open_hours: Current hours windows are open.

    Returns:
        List of up to 5 IndoorHack instances sorted in descending order of delta PM2.5.
    """
    v = max(1.0, room_volume_m3)
    p_hours = set(purifier_on_hours or set())
    w_hours = set(windows_open_hours or set())

    base_res = simulate_indoor_pm25(
        room_volume_m3=v,
        outdoor_pm25_series=outdoor_series,
        windows_open_hours=w_hours,
        purifier_cadr_m3_per_h=purifier_cadr_m3_per_h,
        purifier_on_hours=p_hours,
        source_events=baseline_events,
    )
    base_mean = base_res.mean_pm25_ug_m3
    hacks: list[IndoorHack] = []

    # 1. Eliminate mosquito coils
    if any(e.kind == "src_mosquito_coil" for e in baseline_events):
        h = _eval_hack(
            hack_id="hack_no_mosquito_coil",
            title="Switch from mosquito coil to bed nets or vaporiser",
            advice="A mosquito coil burning overnight emits PM2.5 equivalent to 75-100 cigarettes.",
            source_citation="Liu et al. (2003) Environmental Health Perspectives",
            formula="delta_pm25 = Baseline_Mean - Simulation_Without_Coil",
            v=v,
            outdoor_series=outdoor_series,
            windows_open_hours=w_hours,
            purifier_cadr=purifier_cadr_m3_per_h,
            purifier_hours=p_hours,
            events=[e for e in baseline_events if e.kind != "src_mosquito_coil"],
            base_mean=base_mean,
        )
        if h:
            hacks.append(h)

    # 2. Avoid incense
    if any(e.kind == "src_incense_stick" for e in baseline_events):
        h = _eval_hack(
            hack_id="hack_no_incense",
            title="Pause burning incense sticks indoors on smoggy days",
            advice="Incense sticks emit fine particulate bursts of over 100 mg/h per stick.",
            source_citation="Lin et al. (2008) Atmospheric Environment",
            formula="delta_pm25 = Baseline_Mean - Simulation_Without_Incense",
            v=v,
            outdoor_series=outdoor_series,
            windows_open_hours=w_hours,
            purifier_cadr=purifier_cadr_m3_per_h,
            purifier_hours=p_hours,
            events=[e for e in baseline_events if e.kind != "src_incense_stick"],
            base_mean=base_mean,
        )
        if h:
            hacks.append(h)

    # 3. Kitchen exhaust during frying / tadka
    if any(e.kind in ("src_frying", "src_tadka") for e in baseline_events):
        reduced = [
            IndoorSourceEvent(e.kind, e.start_hour, e.minutes * 0.3, e.count)
            if e.kind in ("src_frying", "src_tadka")
            else e
            for e in baseline_events
        ]
        h = _eval_hack(
            hack_id="hack_kitchen_exhaust",
            title="Turn on kitchen exhaust and lid pans during tadka/frying",
            advice="Kitchen exhaust captures ~70% of frying aerosols before room infiltration.",
            source_citation="Buonanno et al. (2009) Particle emission factors in cooking",
            formula="delta_pm25 = Baseline_Mean - Simulation_With_Exhaust",
            v=v,
            outdoor_series=outdoor_series,
            windows_open_hours=w_hours,
            purifier_cadr=purifier_cadr_m3_per_h,
            purifier_hours=p_hours,
            events=reduced,
            base_mean=base_mean,
        )
        if h:
            hacks.append(h)

    # 4. Seal windows in smog peaks
    peak_hours = {6, 7, 8, 9, 18, 19, 20, 21}
    bad_windows = w_hours.intersection(peak_hours)
    if bad_windows:
        h = _eval_hack(
            hack_id="hack_close_peak_windows",
            title="Keep windows shut during morning and evening smog peaks",
            advice="Temperature inversions trap severe pollution near the ground morning/evening.",
            source_citation="Goel et al. (2015) diurnal ambient winter peak studies",
            formula="delta_pm25 = Baseline_Mean - Simulation_Closed_Peak_Windows",
            v=v,
            outdoor_series=outdoor_series,
            windows_open_hours=w_hours - bad_windows,
            purifier_cadr=purifier_cadr_m3_per_h,
            purifier_hours=p_hours,
            events=baseline_events,
            base_mean=base_mean,
        )
        if h:
            hacks.append(h)

    # 5. Nighttime purifier operation
    sleep_hours = {22, 23, 0, 1, 2, 3, 4, 5}
    if sleep_hours - p_hours:
        effective_cadr = purifier_cadr_m3_per_h if purifier_cadr_m3_per_h > 0 else (v * 5.0)
        h = _eval_hack(
            hack_id="hack_night_purifier",
            title="Run air purifier continuously in the bedroom during sleep",
            advice="People spend ~8 hours in the bedroom; clean night air cuts daily dose.",
            source_citation="US EPA Guide to Air Cleaners in the Home",
            formula="delta_pm25 = Baseline_Mean - Simulation_Night_Purifier",
            v=v,
            outdoor_series=outdoor_series,
            windows_open_hours=w_hours,
            purifier_cadr=effective_cadr,
            purifier_hours=p_hours.union(sleep_hours),
            events=baseline_events,
            base_mean=base_mean,
        )
        if h:
            hacks.append(h)

    hacks.sort(key=lambda item: item.delta_pm25_ug_m3, reverse=True)
    return hacks[:5]
