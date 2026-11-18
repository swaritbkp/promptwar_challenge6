"""Indoor air quality hacks, purifier sizing heuristics, and natural ventilation timing."""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.explain import Explanation
from hawakhata.engine.indoor_model import IndoorSourceEvent, simulate_indoor_pm25

MIN_MEANINGFUL_DELTA_UG_M3 = 0.1
DEFAULT_PURIFIER_ACH = 5.0


@dataclass(frozen=True, slots=True)
class VentilationRecommendation:
    """Airing advice identifying optimal hours for natural cross-ventilation."""

    recommended_hours: list[int]
    qualifying_count: int
    reason: str
    explanation: Explanation


@dataclass(frozen=True, slots=True)
class PurifierRecommendation:
    """Portable HEPA air purifier sizing verdict against target ACH."""

    required_cadr_m3_per_h: float
    current_cadr_m3_per_h: float
    is_sufficient: bool
    deficit_m3_per_h: float
    advice: str
    explanation: Explanation


@dataclass(frozen=True, slots=True)
class IndoorHack:
    """A practical intervention reducing indoor particulate exposure."""

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
    """Identify windows where airing the house reduces indoor PM2.5 (C_out < C_in)."""
    qualifying = [
        (h, outdoor_series[h])
        for h in range(min(len(outdoor_series), len(indoor_baseline_series), 24))
        if outdoor_series[h] < indoor_baseline_series[h]
    ]
    qualifying.sort(key=lambda x: x[1])
    chosen = [h for h, _ in qualifying[:max_hours]]

    if chosen:
        formatted = ", ".join(f"{h:02d}:00" for h in sorted(chosen))
        reason = (
            f"Outdoor air is cleaner than indoor during {formatted}. "
            "Open windows during these cleanest hours to flush indoor particulates."
        )
    else:
        reason = "Outdoor air is more polluted than indoor throughout the day. Keep windows closed."

    return VentilationRecommendation(
        recommended_hours=chosen,
        qualifying_count=len(qualifying),
        reason=reason,
        explanation=Explanation(
            "C_out(h) < C_in(h), sorted by min C_out",
            {"qualifying_count": len(qualifying), "chosen_hours": chosen},
            ["air_exchange_open", "air_exchange_closed"],
            ["EPA/WHO indoor-outdoor exchange guidance"],
            ["Cross-ventilation achieves 3.0 ACH when open"],
        ),
    )


def recommend_purifier_cadr(
    room_volume_m3: float,
    current_cadr_m3_per_h: float = 0.0,
    target_ach: float = DEFAULT_PURIFIER_ACH,
) -> PurifierRecommendation:
    """Evaluate whether air purifier CADR is adequate (Required_CADR = Volume * Target_ACH)."""
    v = max(1.0, room_volume_m3)
    required = v * target_ach
    deficit = max(0.0, required - current_cadr_m3_per_h)
    sufficient = current_cadr_m3_per_h >= required

    if sufficient:
        advice = (
            f"Your purifier ({current_cadr_m3_per_h:.0f} m³/h CADR) is sufficient for this "
            f"{v:.0f} m³ room. Run continuously in bedroom."
        )
    else:
        advice = (
            f"This {v:.0f} m³ room needs at least {required:.0f} m³/h CADR "
            f"(deficit of {deficit:.0f} m³/h). Move closer to bed or add CADR."
        )

    return PurifierRecommendation(
        required_cadr_m3_per_h=required,
        current_cadr_m3_per_h=current_cadr_m3_per_h,
        is_sufficient=sufficient,
        deficit_m3_per_h=deficit,
        advice=advice,
        explanation=Explanation(
            "Required_CADR = Room_Volume * Target_ACH",
            {
                "room_volume_m3": v,
                "current_cadr": current_cadr_m3_per_h,
                "target_ach": target_ach,
                "required_cadr": required,
            },
            ["purifier_target_ach"],
            ["AHAM AC-1", "US EPA Guide to Air Cleaners in the Home"],
            ["5 ACH for severe smog"],
        ),
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
    res = simulate_indoor_pm25(
        room_volume_m3=v,
        outdoor_pm25_series=outdoor_series,
        windows_open_hours=windows_open_hours,
        purifier_cadr_m3_per_h=purifier_cadr,
        purifier_on_hours=purifier_hours,
        source_events=events,
    )
    delta = base_mean - res.mean_pm25_ug_m3
    if delta < MIN_MEANINGFUL_DELTA_UG_M3:
        return None
    return IndoorHack(
        id=hack_id,
        title=title,
        delta_pm25_ug_m3=round(delta, 1),
        advice=advice,
        explanation=Explanation(
            formula,
            {
                "baseline_mean_pm25": round(base_mean, 1),
                "intervention_mean_pm25": round(res.mean_pm25_ug_m3, 1),
                "delta_saved": round(delta, 1),
            },
            ["indoor_emission_rate"],
            [source_citation],
            ["Intervention applied across full 24h cycle"],
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
    """Rank up to 5 indoor interventions by descending modeled PM2.5 reduction."""
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

    def _run(
        h_id: str,
        title: str,
        advice: str,
        src: str,
        formula: str,
        *,
        win: set[int] | None = None,
        cadr: float | None = None,
        p_h: set[int] | None = None,
        ev: list[IndoorSourceEvent] | None = None,
    ) -> None:
        h = _eval_hack(
            hack_id=h_id,
            title=title,
            advice=advice,
            source_citation=src,
            formula=formula,
            v=v,
            outdoor_series=outdoor_series,
            windows_open_hours=w_hours if win is None else win,
            purifier_cadr=purifier_cadr_m3_per_h if cadr is None else cadr,
            purifier_hours=p_hours if p_h is None else p_h,
            events=baseline_events if ev is None else ev,
            base_mean=base_mean,
        )
        if h:
            hacks.append(h)

    if any(e.kind == "src_mosquito_coil" for e in baseline_events):
        _run(
            "hack_no_mosquito_coil",
            "Switch from mosquito coil to bed nets or vaporiser",
            "A mosquito coil emits PM2.5 equivalent to 75-100 cigarettes.",
            "Liu et al. (2003)",
            "delta_pm25 = Base - Sim_No_Coil",
            ev=[e for e in baseline_events if e.kind != "src_mosquito_coil"],
        )

    if any(e.kind == "src_incense_stick" for e in baseline_events):
        _run(
            "hack_no_incense",
            "Pause burning incense sticks indoors on smoggy days",
            "Incense sticks emit fine particulate bursts over 100 mg/h.",
            "Lin et al. (2008)",
            "delta_pm25 = Base - Sim_No_Incense",
            ev=[e for e in baseline_events if e.kind != "src_incense_stick"],
        )

    if any(e.kind in ("src_frying", "src_tadka") for e in baseline_events):
        reduced = [
            IndoorSourceEvent(e.kind, e.start_hour, e.minutes * 0.3, e.count)
            if e.kind in ("src_frying", "src_tadka")
            else e
            for e in baseline_events
        ]
        _run(
            "hack_kitchen_exhaust",
            "Turn on kitchen exhaust and lid pans during tadka/frying",
            "Kitchen exhaust captures ~70% of frying aerosols.",
            "Buonanno et al. (2009)",
            "delta_pm25 = Base - Sim_Exhaust",
            ev=reduced,
        )

    peak_hours = {6, 7, 8, 9, 18, 19, 20, 21}
    bad_windows = w_hours.intersection(peak_hours)
    if bad_windows:
        _run(
            "hack_close_peak_windows",
            "Keep windows shut during morning and evening smog peaks",
            "Inversions trap severe pollution near ground during peaks.",
            "Goel et al. (2015)",
            "delta_pm25 = Base - Sim_Closed_Peaks",
            win=w_hours - bad_windows,
        )

    sleep_hours = {22, 23, 0, 1, 2, 3, 4, 5}
    if sleep_hours - p_hours:
        effective_cadr = purifier_cadr_m3_per_h if purifier_cadr_m3_per_h > 0 else (v * 5.0)
        _run(
            "hack_night_purifier",
            "Run air purifier continuously in the bedroom during sleep",
            "Clean bedroom air cuts overnight exposure.",
            "US EPA Guide to Air Cleaners",
            "delta_pm25 = Base - Sim_Night_Purifier",
            cadr=effective_cadr,
            p_h=p_hours.union(sleep_hours),
        )

    hacks.sort(key=lambda item: item.delta_pm25_ug_m3, reverse=True)
    return hacks[:5]
