from __future__ import annotations

from hawakhata.engine.indoor_model import IndoorSourceEvent
from hawakhata.engine.recommendations import (
    _eval_hack,
    rank_indoor_hacks,
    recommend_purifier_cadr,
    recommend_ventilation_hours,
)


def test_recommend_ventilation_hours_some_qualify() -> None:
    indoor = [100.0] * 24
    outdoor = [200.0] * 24
    outdoor[13] = 45.0
    outdoor[14] = 40.0
    outdoor[15] = 50.0

    rec = recommend_ventilation_hours(outdoor, indoor, max_hours=2)
    assert rec.recommended_hours == [14, 13]
    assert rec.qualifying_count == 3
    assert "cleanest" in rec.reason.lower()


def test_recommend_ventilation_hours_none_qualify_on_severe_day() -> None:
    indoor = [120.0] * 24
    outdoor = [300.0] * 24

    rec = recommend_ventilation_hours(outdoor, indoor, max_hours=3)
    assert rec.recommended_hours == []
    assert rec.qualifying_count == 0
    assert "more polluted" in rec.reason.lower()


def test_recommend_purifier_cadr() -> None:
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

    outdoor_severe = [400.0] * 24
    hacks_severe = rank_indoor_hacks(
        room_volume_m3=35.0,
        outdoor_series=outdoor_severe,
        baseline_events=[],
        windows_open_hours={7, 8, 19},
    )
    assert any(h.id == "hack_close_peak_windows" for h in hacks_severe)


def test_rank_indoor_hacks_edge_branches() -> None:
    sleep_hours = {22, 23, 0, 1, 2, 3, 4, 5}
    outdoor = [100.0] * 24
    hacks = rank_indoor_hacks(
        room_volume_m3=40.0,
        outdoor_series=outdoor,
        baseline_events=[],
        purifier_cadr_m3_per_h=200.0,
        purifier_on_hours=sleep_hours,
    )
    assert not any(h.id == "hack_night_purifier" for h in hacks)

    tadka_events = [IndoorSourceEvent(kind="src_tadka", start_hour=19, minutes=15.0)]
    hacks_tadka = rank_indoor_hacks(
        room_volume_m3=40.0,
        outdoor_series=outdoor,
        baseline_events=tadka_events,
    )
    assert any(h.id == "hack_kitchen_exhaust" for h in hacks_tadka)

    none_hack = _eval_hack(
        hack_id="negligible",
        title="Zero delta hack",
        advice="No effect",
        source_citation="Test",
        formula="0",
        v=50.0,
        outdoor_series=[0.0] * 24,
        windows_open_hours=set(),
        purifier_cadr=0.0,
        purifier_hours=set(),
        events=[],
        base_mean=0.0,
    )
    assert none_hack is None

    tiny_events = [
        IndoorSourceEvent(kind="src_mosquito_coil", start_hour=22, minutes=0.01),
        IndoorSourceEvent(kind="src_incense_stick", start_hour=7, minutes=0.01),
        IndoorSourceEvent(kind="src_frying", start_hour=12, minutes=0.01),
    ]
    hacks_tiny = rank_indoor_hacks(
        room_volume_m3=100000.0,
        outdoor_series=[1.0] * 24,
        baseline_events=tiny_events,
        windows_open_hours={7},
        purifier_on_hours=sleep_hours,
    )
    assert hacks_tiny == []
