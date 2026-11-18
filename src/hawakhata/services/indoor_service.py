"""Indoor environment service integrating mass-balance PM2.5 simulation and IAQ hacks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hawakhata.api.schemas import RoomInput, SourceEventInput
from hawakhata.engine.indoor_model import (
    IndoorSourceEvent,
    simulate_indoor_pm25,
)
from hawakhata.engine.recommendations import (
    rank_indoor_hacks,
    recommend_purifier_cadr,
    recommend_ventilation_hours,
)


@dataclass(frozen=True, slots=True)
class IndoorEnvironmentResult:
    """Consolidated indoor simulation report with actionable interventions."""

    room_name: str
    simulation: dict[str, Any]
    purifier_recommendation: dict[str, Any]
    ventilation_recommendation: dict[str, Any]
    ranked_hacks: list[dict[str, Any]]


def simulate_indoor_environment(
    room: RoomInput,
    sources: list[SourceEventInput],
    outdoor_pm25_series: list[float],
) -> IndoorEnvironmentResult:
    """Run full indoor mass-balance simulation, purifier sizing, and intervention ranking."""
    events = [
        IndoorSourceEvent(
            kind=s.kind,
            start_hour=s.start_hour,
            minutes=s.minutes,
            count=s.count,
        )
        for s in sources
    ]

    sim_res = simulate_indoor_pm25(
        room_volume_m3=room.volume_m3,
        outdoor_pm25_series=outdoor_pm25_series,
        windows_open_hours=set(room.windows_open_hours),
        purifier_cadr_m3_per_h=room.purifier_cadr_m3_per_h,
        purifier_on_hours=set(room.purifier_on_hours),
        source_events=events,
    )

    purifier_rec = recommend_purifier_cadr(
        room_volume_m3=room.volume_m3,
        current_cadr_m3_per_h=room.purifier_cadr_m3_per_h,
    )

    vent_rec = recommend_ventilation_hours(
        outdoor_series=outdoor_pm25_series,
        indoor_baseline_series=sim_res.hourly_pm25_ug_m3,
    )

    hacks = rank_indoor_hacks(
        room_volume_m3=room.volume_m3,
        outdoor_series=outdoor_pm25_series,
        baseline_events=events,
        purifier_cadr_m3_per_h=room.purifier_cadr_m3_per_h,
        windows_open_hours=set(room.windows_open_hours),
        purifier_on_hours=set(room.purifier_on_hours),
    )

    return IndoorEnvironmentResult(
        room_name=room.name,
        simulation=asdict(sim_res),
        purifier_recommendation=asdict(purifier_rec),
        ventilation_recommendation=asdict(vent_rec),
        ranked_hacks=[asdict(h) for h in hacks],
    )
