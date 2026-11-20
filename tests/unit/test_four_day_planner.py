"""Unit tests for 4-day predictive engine, dispersion regimes, and multi-day scheduler."""

from __future__ import annotations

from hawakhata.engine.planner import (
    build_four_day_outlook,
    classify_dispersion,
    compute_waking_cleanest_window,
    optimize_multi_day_activity,
)


def test_classify_dispersion_regimes() -> None:
    assert classify_dispersion(5.0, 200.0, 90.0, 2.5)[0] == "Rain Washout"
    assert classify_dispersion(19.5, 400.0, 60.0, 0.0)[0] == "Wind Clearing"
    assert classify_dispersion(10.0, 1100.0, 40.0, 0.0)[0] == "Afternoon Mixing Lift"
    assert classify_dispersion(4.0, 220.0, 85.0, 0.0)[0] == "Inversion Trap"
    assert classify_dispersion(6.0, 500.0, 70.0, 0.0)[0] == "Stagnant Air"


def test_build_four_day_outlook_and_watch() -> None:
    pm = [320.0 if (h % 24 < 9 or h % 24 > 19) else 85.0 for h in range(96)]
    outlook = build_four_day_outlook(pm)
    assert len(outlook.days) == 4
    assert [d.day_label for d in outlook.days] == ["Today", "Tomorrow", "Day 3", "Day 4"]
    day_aqis = [d.peak_aqi for d in outlook.days]
    assert len(set(day_aqis)) >= 2
    assert all(d.cleanest_pm25 < 150.0 for d in outlook.days)
    assert 11 <= int(outlook.safe_house_flush.start_hour[:2]) <= 16
    assert outlook.safe_house_flush.outdoor_pm25 < 150.0

    # Test canonical waking cleanest window
    c_start, c_end, c_avg = compute_waking_cleanest_window(pm[:24], window_hours=3)
    assert 6 <= c_start <= 17 and c_end == c_start + 3
    assert c_avg <= 100.0

    out_w = build_four_day_outlook([50.0] * 24 + [250.0] * 24 + [100.0] * 48)
    assert (
        out_w.tomorrow_watch_direction == "worsens" and "worsens" in out_w.tomorrow_watch_headline
    )

    out_i = build_four_day_outlook([250.0] * 24 + [50.0] * 24 + [100.0] * 48)
    assert (
        out_i.tomorrow_watch_direction == "improves" and "improves" in out_i.tomorrow_watch_headline
    )


def test_optimize_multi_day_activity() -> None:
    pm = [70.0 if 12 <= (h % 24) <= 15 else 350.0 for h in range(96)]
    slots = optimize_multi_day_activity("adult", "walk", 60, pm)
    assert len(slots) == 3 and [s.rank for s in slots] == [1, 2, 3]
    for s in slots:
        assert 6 <= s.start_hour <= 19 and s.savings_ug > 0.0 and s.savings_pct > 0.0


def test_four_day_outlook_distinct_peak_aqis_metro_cities() -> None:
    from hawakhata.integrations.air_quality import _load_nearest_fixture

    metros = {
        "Gurugram": (28.4595, 77.0266),
        "Chandigarh": (30.7333, 76.7794),
        "Mumbai": (19.0760, 72.8777),
    }

    for name, (lat, lng) in metros.items():
        series = _load_nearest_fixture(lat, lng, 96)
        pm_series = [p.pm25_ug_m3 for p in series.points]
        outlook = build_four_day_outlook(pm_series)
        day_aqis = [d.peak_aqi for d in outlook.days]
        # Must yield at least 3 distinct daily Peak AQIs
        assert len(set(day_aqis)) >= 3, f"{name} peak AQIs not distinct enough: {day_aqis}"
        # A genuinely cleaner recommended day must exist
        cleanest_day = min(outlook.days, key=lambda d: d.peak_aqi)
        dirtiest_day = max(outlook.days, key=lambda d: d.peak_aqi)
        assert cleanest_day.peak_aqi < dirtiest_day.peak_aqi
        assert cleanest_day.cleanest_pm25 < dirtiest_day.peak_pm25
