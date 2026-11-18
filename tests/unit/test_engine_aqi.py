from __future__ import annotations

import pytest

from hawakhata.engine.aqi import (
    aqi_to_category,
    pm25_to_naqi_category,
    pm25_to_sub_index,
)


@pytest.mark.parametrize(
    ("pm25", "expected_code", "expected_icon"),
    [
        (0.0, "good", "smile"),
        (15.0, "good", "smile"),
        (30.0, "good", "smile"),
        (30.1, "satisfactory", "leaf"),
        (31.0, "satisfactory", "leaf"),
        (60.0, "satisfactory", "leaf"),
        (60.1, "moderate", "cloud"),
        (90.0, "moderate", "cloud"),
        (90.1, "poor", "haze"),
        (120.0, "poor", "haze"),
        (120.1, "very_poor", "mask"),
        (250.0, "very_poor", "mask"),
        (250.1, "severe", "warning_triangle"),
        (450.0, "severe", "warning_triangle"),
        (999.0, "severe", "warning_triangle"),
    ],
)
def test_pm25_to_naqi_category_boundaries(
    pm25: float, expected_code: str, expected_icon: str
) -> None:
    cat = pm25_to_naqi_category(pm25)
    assert cat.code == expected_code
    assert cat.icon_key == expected_icon
    assert cat.label_key == f"naqi.category.{expected_code}"
    assert cat.color_hex.startswith("#")


@pytest.mark.parametrize(
    ("aqi", "expected_code"),
    [
        (0, "good"),
        (50, "good"),
        (51, "satisfactory"),
        (100, "satisfactory"),
        (101, "moderate"),
        (200, "moderate"),
        (201, "poor"),
        (300, "poor"),
        (301, "very_poor"),
        (400, "very_poor"),
        (401, "severe"),
        (500, "severe"),
        (850, "severe"),
    ],
)
def test_aqi_to_category_boundaries(aqi: int, expected_code: str) -> None:
    cat = aqi_to_category(aqi)
    assert cat.code == expected_code


def test_pm25_to_sub_index_values() -> None:
    assert pm25_to_sub_index(0.0) == 0
    assert pm25_to_sub_index(30.0) == 50
    assert pm25_to_sub_index(60.0) == 100
    assert pm25_to_sub_index(90.0) == 200
    assert pm25_to_sub_index(120.0) == 300
    assert pm25_to_sub_index(250.0) == 400
    assert pm25_to_sub_index(380.0) > 400
    assert pm25_to_sub_index(500.0) == 500
    assert pm25_to_sub_index(625.0) == 550


def test_negative_pm25_clamps_or_raises() -> None:
    cat = pm25_to_naqi_category(-5.0)
    assert cat.code == "good"
    assert pm25_to_sub_index(-10.0) == 0
