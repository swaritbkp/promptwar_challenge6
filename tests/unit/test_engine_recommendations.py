from __future__ import annotations

from hawakhata.engine.indoor_model import IndoorSourceEvent
from hawakhata.engine.recommendations import (
    _eval_hack,
    rank_indoor_hacks,
    recommend_purifier_cadr,
    recommend_ventilation_hours,
)


def test_recommend_ventilation_hours_some_qualify() -> None:
    indoor, outdoor = [100.0] * 24, [200.0] * 24
    outdoor[13], outdoor[14], outdoor[15] = 45.0, 40.0, 50.0
    rec = recommend_ventilation_hours(outdoor, indoor, max_hours=2)
    assert (
        rec.recommended_hours == [14, 13]
        and rec.qualifying_count == 3
        and "cleaner" in rec.reason.lower()
    )


def test_recommend_ventilation_hours_none_qualify_on_severe_day() -> None:
    rec = recommend_ventilation_hours([300.0] * 24, [120.0] * 24, max_hours=3)
    assert rec.recommended_hours == [] and "more polluted" in rec.reason.lower()


def test_recommend_purifier_cadr() -> None:
    assert recommend_purifier_cadr(50.0, 150.0).is_sufficient is False
    assert recommend_purifier_cadr(50.0, 300.0).is_sufficient is True


def test_rank_indoor_hacks_all_branches() -> None:
    events = [
        IndoorSourceEvent("src_frying", 12, 30.0),
        IndoorSourceEvent("src_mosquito_coil", 22, 60.0),
        IndoorSourceEvent("src_incense_stick", 7, 30.0),
    ]
    hacks = rank_indoor_hacks(35.0, [180.0] * 24, events, windows_open_hours={14})
    h_ids = [h.id for h in hacks]
    for expected in [
        "hack_kitchen_exhaust",
        "hack_night_purifier",
        "hack_no_incense",
        "hack_no_mosquito_coil",
    ]:
        assert expected in h_ids
    assert any(
        h.id == "hack_close_peak_windows"
        for h in rank_indoor_hacks(35.0, [400.0] * 24, [], windows_open_hours={7, 8, 19})
    )


def test_rank_indoor_hacks_edge_branches() -> None:
    sleep = {22, 23, 0, 1, 2, 3, 4, 5}
    assert not any(
        h.id == "hack_night_purifier"
        for h in rank_indoor_hacks(
            40.0, [100.0] * 24, [], purifier_cadr_m3_per_h=200.0, purifier_on_hours=sleep
        )
    )
    assert any(
        h.id == "hack_kitchen_exhaust"
        for h in rank_indoor_hacks(40.0, [100.0] * 24, [IndoorSourceEvent("src_tadka", 19, 15.0)])
    )
    assert (
        _eval_hack(
            "n",
            "Z",
            "N",
            "T",
            "0",
            v=50.0,
            outdoor_series=[0.0] * 24,
            windows_open_hours=set(),
            purifier_cadr=0.0,
            purifier_hours=set(),
            events=[],
            base_mean=0.0,
        )
        is None
    )
    assert (
        rank_indoor_hacks(
            100000.0,
            [1.0] * 24,
            [IndoorSourceEvent("src_mosquito_coil", 22, 0.01)],
            purifier_on_hours=sleep,
        )
        == []
    )
