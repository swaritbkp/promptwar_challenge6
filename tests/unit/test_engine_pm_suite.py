"""Mask filtration, GRAP stages, 3-slot day summary, clock alignment and NAQI parity."""

from __future__ import annotations

import pytest

from hawakhata.engine.aqi import (
    aqi_to_grap_stage,
    pm25_to_naqi_category,
    pm25_to_sub_index,
)
from hawakhata.engine.budget import daily_air_budget_ug
from hawakhata.engine.constants import get_constant
from hawakhata.engine.dose import (
    MASK_TYPES,
    compute_masked_activity_dose,
    inhalation_rate_m3_per_h,
    mask_filtration_factor,
)
from hawakhata.engine.planner import (
    align_to_clock,
    build_four_day_outlook,
    optimize_multi_day_activity,
    summarize_day_parts,
)

# --- Mask filtration -------------------------------------------------------------------


def test_mask_factors_come_from_constants() -> None:
    assert get_constant("mask_filtration_factor").value == {
        "none": 1.0,
        "surgical": 0.65,
        "n95": 0.15,
    }
    assert [mask_filtration_factor(m) for m in MASK_TYPES] == [1.0, 0.65, 0.15]
    with pytest.raises(KeyError):
        mask_filtration_factor("cloth")


def test_masked_dose_math_and_budget_verdict() -> None:
    budget = daily_air_budget_ug("senior")
    ir = inhalation_rate_m3_per_h("senior", "walk")
    none = compute_masked_activity_dose("senior", "walk", [300.0, 200.0], 60, "none", budget)
    n95 = compute_masked_activity_dose("senior", "walk", [300.0, 200.0], 60, "n95", budget)
    surg = compute_masked_activity_dose("senior", "walk", [300.0, 200.0], 60, "surgical", budget)
    assert none.unmasked_dose_ug == pytest.approx(round(250.0 * ir, 1))
    assert none.masked_dose_ug == none.unmasked_dose_ug and none.mask_saved_ug == 0.0
    assert n95.masked_dose_ug == pytest.approx(round(250.0 * ir * 0.15, 1), abs=0.1)
    assert n95.masked_dose_ug < surg.masked_dose_ug < none.masked_dose_ug
    assert n95.mask_saved_ug == pytest.approx(n95.unmasked_dose_ug - n95.masked_dose_ug, abs=0.1)
    assert n95.budget_share_pct == pytest.approx(n95.masked_dose_ug / budget * 100, abs=0.1)
    long_none = compute_masked_activity_dose("senior", "run", [300.0], 120, "none", budget)
    long_n95 = compute_masked_activity_dose("senior", "run", [300.0], 120, "n95", budget)
    assert long_none.within_budget is False and long_n95.within_budget is True
    assert "mask_filtration_factor" in n95.explanation.constants_used


# --- GRAP -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("aqi", "stage", "code"),
    [
        (0, 0, "normal"),
        (200, 0, "normal"),
        (201, 1, "I"),
        (300, 1, "I"),
        (301, 2, "II"),
        (400, 2, "II"),
        (401, 3, "III"),
        (450, 3, "III"),
        (451, 4, "IV"),
        (500, 4, "IV"),
    ],
)
def test_grap_stage_boundaries(aqi: int, stage: int, code: str) -> None:
    g = aqi_to_grap_stage(aqi)
    assert (g.stage, g.code, g.aqi) == (stage, code, aqi)
    assert g.advisories_en and len(g.advisories_en) == len(g.advisories_hi)
    assert "CAQM" in g.scope_note_en and g.label_hi


# --- NAQI parity with constants.v1.json -------------------------------------------------


def test_naqi_band_edges_match_constants_file() -> None:
    rows = get_constant("naqi_pm25_breakpoints").value
    for _low, high, code in rows[:-1]:
        assert pm25_to_naqi_category(float(high)).code == code  # upper edge -> same band
        assert pm25_to_naqi_category(float(high) + 0.4).code != code  # 30.4 -> next band
    assert pm25_to_sub_index(30.0) == 50 and pm25_to_sub_index(30.4) == 51
    assert pm25_to_sub_index(250.0) == 400 and pm25_to_naqi_category(251).code == "severe"


# --- Clock alignment & 3-slot brief -----------------------------------------------------


def test_align_to_clock_rotates_each_day_chunk() -> None:
    series = list(range(48))  # reading i taken at clock hour (18 + i) % 24
    aligned = align_to_clock(series, 18)
    assert len(aligned) == 48
    assert aligned[18] == 0 and aligned[23] == 5 and aligned[0] == 6 and aligned[17] == 23
    assert aligned[24 + 18] == 24
    assert align_to_clock(series, 0) == series and align_to_clock([], 5) == []


def test_day_parts_morning_afternoon_evening() -> None:
    clock = [300.0] * 6 + [250.0] * 6 + [55.0] * 5 + [140.0] * 5 + [300.0] * 2
    parts = summarize_day_parts(clock)
    assert [(p.part, p.start_hour, p.end_hour) for p in parts] == [
        ("morning", 6, 11),
        ("afternoon", 12, 16),
        ("evening", 17, 21),
    ]
    assert [p.mean_pm25 for p in parts] == [250.0, 55.0, 140.0]
    assert [p.category_code for p in parts] == ["very_poor", "satisfactory", "very_poor"]
    assert parts[1].aqi == pm25_to_sub_index(55.0)
    assert parts[0].guidance_en and parts[0].guidance_hi and parts[0].label_hi == "सुबह"


def _inversion_day() -> list[float]:
    """Clock-hour profile: severe 07:00 inversion, clean 13:00-16:00 mixing lift."""
    day = [260.0] * 24
    day[6], day[7], day[8] = 330.0, 345.0, 320.0
    day[13], day[14], day[15], day[16] = 158.0, 115.0, 121.0, 150.0
    return day


def test_four_day_cleanest_window_uses_true_clock_hours_when_series_starts_at_18h() -> None:
    start = 18  # live series start "now" = 18:00 IST
    # Reading i is clock hour (18 + i) % 24; each forecast day is 1 ug/m3 dirtier (live data).
    shifted = [_inversion_day()[(start + i) % 24] + i // 24 for i in range(96)]
    out = build_four_day_outlook(shifted, None, start_hour=start)
    for d, day in enumerate(out.days):
        # Afternoon (13-16h) must beat the 06-09h morning inversion on every day.
        assert (day.cleanest_window_start, day.cleanest_window_end) == ("14:00", "17:00")
        assert day.cleanest_pm25 == pytest.approx((115.0 + 121.0 + 150.0) / 3 + d, abs=0.1)
    # Without alignment the same data would yield the misleading 06:00-09:00 window.
    naive = build_four_day_outlook(shifted, None)
    assert naive.days[0].cleanest_window_start != "14:00"


def test_multi_day_slots_use_clock_hours() -> None:
    start = 18
    shifted = [_inversion_day()[(start + i) % 24] + i // 24 for i in range(96)]
    slots = optimize_multi_day_activity("31_41", "walk", 60, shifted, None, start_hour=start)
    assert slots[0].day_index == 0 and slots[0].start_hour == 14
    assert slots[0].outdoor_pm25 == 115.0 and all(s.start_hour == 14 for s in slots)
