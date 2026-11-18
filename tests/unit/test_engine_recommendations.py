from __future__ import annotations

from hawakhata.engine.indoor_model import IndoorSourceEvent
from hawakhata.engine.recommendations import (
    rank_indoor_hacks,
    recommend_purifier_cadr,
    recommend_ventilation_hours,
)


def test_recommend_ventilation_hours_some_qualify() -> None:
    # Indoor baseline is 100 ug/m3. Outdoor is 50 ug/m3 at hours 13, 14, 15 and 200 ug/m3 elsewhere
    indoor = [100.0] * 24
    outdoor = [200.0] * 24
    outdoor[13] = 45.0
    outdoor[14] = 40.0
    outdoor[15] = 50.0

    rec = recommend_ventilation_hours(outdoor, indoor, max_hours=2)
    assert rec.recommended_hours == [14, 13]  # sorted by lowest outdoor PM2.5
    assert rec.qualifying_count == 3
    assert "cleanest" in rec.reason.lower()


def test_recommend_ventilation_hours_none_qualify_on_severe_day() -> None:
    # Outdoor is 300 ug/m3 everywhere, indoor is 120 ug/m3
    indoor = [120.0] * 24
    outdoor = [300.0] * 24

    rec = recommend_ventilation_hours(outdoor, indoor, max_hours=3)
    assert rec.recommended_hours == []
    assert rec.qualifying_count == 0
    assert "more polluted" in rec.reason.lower()


def test_recommend_purifier_cadr() -> None:
    # 50 m3 room * 5 ACH = 250 m3/h required
    rec_deficit = recommend_purifier_cadr(room_volume_m3=50.0, current_cadr_m3_per_h=150.0)
    assert rec_deficit.required_cadr_m3_per_h == 250.0
    assert rec_deficit.is_sufficient is False
    assert rec_deficit.deficit_m3_per_h == 100.0

    rec_ok = recommend_purifier_cadr(room_volume_m3=50.0, current_cadr_m3_per_h=300.0)
    assert rec_ok.is_sufficient is True
    assert rec_ok.deficit_m3_per_h == 0.0


def test_rank_indoor_hacks_all_branches() -> None:
    events = [
        IndoorSourceEvent(kind="src_frying", start_hour=12, minutes=30.0),
        IndoorSourceEvent(kind="src_mosquito_coil", start_hour=22, minutes=60.0),
        IndoorSourceEvent(kind="src_incense_stick", start_hour=7, minutes=30.0),
    ]
    outdoor = [180.0] * 24
    hacks = rank_indoor_hacks(
        room_volume_m3=35.0,
        outdoor_series=outdoor,
        baseline_events=events,
        purifier_cadr_m3_per_h=0.0,
        windows_open_hours={14},
        purifier_on_hours=set(),
    )
    hack_ids = [h.id for h in hacks]
    assert "hack_kitchen_exhaust" in hack_ids
    assert "hack_night_purifier" in hack_ids
    assert "hack_no_incense" in hack_ids
    assert "hack_no_mosquito_coil" in hack_ids

    # When outdoor peak is very high and windows open in peak, close windows is recommended
    outdoor_severe = [400.0] * 24
    hacks_severe = rank_indoor_hacks(
        room_volume_m3=35.0,
        outdoor_series=outdoor_severe,
        baseline_events=[],
        windows_open_hours={7, 8, 19},
    )
    assert any(h.id == "hack_close_peak_windows" for h in hacks_severe)
