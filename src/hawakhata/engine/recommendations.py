"""Indoor air hacks and purifier sizing utilities."""

from __future__ import annotations

from dataclasses import dataclass

from hawakhata.engine.explain import Explanation
from hawakhata.engine.indoor_model import IndoorSourceEvent, simulate_indoor_pm25


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
    outdoor_series: list[float], indoor_baseline_series: list[float], max_hours: int = 3
) -> VentilationRecommendation:
    """Identify windows where airing the house reduces indoor PM2.5 (C_out < C_in)."""
    qualifying = [
        (h, outdoor_series[h])
        for h in range(min(len(outdoor_series), len(indoor_baseline_series), 24))
        if outdoor_series[h] < indoor_baseline_series[h]
    ]
    qualifying.sort(key=lambda x: x[1])
    chosen = [h for h, _ in qualifying[:max_hours]]
    win_str = ", ".join(f"{h:02d}:00" for h in sorted(chosen))
    reason = (
        f"Outdoor air is cleaner than indoor during {win_str}. Open windows."
        if chosen
        else "Outdoor air is more polluted than indoor throughout the day. Keep windows closed."
    )
    return VentilationRecommendation(
        recommended_hours=chosen,
        qualifying_count=len(qualifying),
        reason=reason,
        explanation=Explanation(
            "C_out(h) < C_in(h)",
            {"count": len(qualifying), "hours": chosen},
            ["air_exchange_open", "air_exchange_closed"],
            ["EPA/WHO"],
            ["Cross-ventilation 3 ACH"],
        ),
    )


def recommend_purifier_cadr(
    room_volume_m3: float,
    current_cadr_m3_per_h: float = 0.0,
    target_ach: float = 5.0,
) -> PurifierRecommendation:
    """Evaluate whether air purifier CADR is adequate (Required_CADR = Volume * Target_ACH)."""
    v = max(1.0, room_volume_m3)
    required = v * target_ach
    deficit = max(0.0, required - current_cadr_m3_per_h)
    sufficient = current_cadr_m3_per_h >= required
    advice = (
        f"Your purifier is sufficient for this {v:.0f} m³ room. Run in bedroom."
        if sufficient
        else f"Room needs {required:.0f} m³/h CADR (deficit {deficit:.0f} m³/h). Add CADR."
    )
    return PurifierRecommendation(
        required_cadr_m3_per_h=required,
        current_cadr_m3_per_h=current_cadr_m3_per_h,
        is_sufficient=sufficient,
        deficit_m3_per_h=deficit,
        advice=advice,
        explanation=Explanation(
            "Required_CADR = Room_Volume * Target_ACH",
            {"volume": v, "target_ach": target_ach, "cadr": current_cadr_m3_per_h},
            ["purifier_target_ach"],
            ["AHAM AC-1", "US EPA"],
            ["5 ACH for severe smog"],
        ),
    )


def _eval_hack(
    hack_id: str,
    title: str,
    advice: str,
    src: str,
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
    if delta < 0.1:
        return None
    return IndoorHack(
        id=hack_id,
        title=title,
        delta_pm25_ug_m3=round(delta, 1),
        advice=advice,
        explanation=Explanation(
            formula,
            {
                "base": round(base_mean, 1),
                "sim": round(res.mean_pm25_ug_m3, 1),
                "saved": round(delta, 1),
            },
            ["indoor_emission_rate"],
            [src],
            ["24h cycle"],
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
            src=src,
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
            "Switch mosquito coil to vaporiser",
            "Mosquito coil emits 75-100 cigarettes.",
            "Liu (2003)",
            "Base - No_Coil",
            ev=[e for e in baseline_events if e.kind != "src_mosquito_coil"],
        )
    if any(e.kind == "src_incense_stick" for e in baseline_events):
        _run(
            "hack_no_incense",
            "Pause incense sticks on smoggy days",
            "Incense emits bursts >100 mg/h.",
            "Lin (2008)",
            "Base - No_Incense",
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
            "Turn on kitchen exhaust and lid pans",
            "Exhaust captures ~70% frying aerosols.",
            "Buonanno (2009)",
            "Base - Exhaust",
            ev=reduced,
        )
    bad_windows = w_hours.intersection({6, 7, 8, 9, 18, 19, 20, 21})
    if bad_windows:
        _run(
            "hack_close_peak_windows",
            "Keep windows shut during smog peaks",
            "Inversions trap peak pollution.",
            "Goel (2015)",
            "Base - Closed_Peaks",
            win=w_hours - bad_windows,
        )
    sleep_hours = {22, 23, 0, 1, 2, 3, 4, 5}
    if sleep_hours - p_hours:
        _run(
            "hack_night_purifier",
            "Run air purifier in bedroom during sleep",
            "Clean bedroom air cuts overnight exposure.",
            "US EPA",
            "Base - Night_Purifier",
            cadr=purifier_cadr_m3_per_h if purifier_cadr_m3_per_h > 0 else (v * 5.0),
            p_h=p_hours.union(sleep_hours),
        )

    hacks.sort(key=lambda item: item.delta_pm25_ug_m3, reverse=True)
    return hacks[:5]
