from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hawakhata.engine.budget import (
    build_passbook_entry,
    daily_air_budget_ug,
)


def test_daily_air_budget_calculation() -> None:
    # Child 6_11: mean IR = 12.0 m3/day -> budget = 15 * 12.0 = 180.0 ug
    b_child = daily_air_budget_ug("6_11")
    assert b_child == 180.0

    # Adult 31_41: mean IR = 16.0 m3/day -> budget = 15 * 16.0 = 240.0 ug
    b_adult = daily_air_budget_ug("31_41")
    assert b_adult == 240.0


def test_build_passbook_entry_under_budget() -> None:
    entry = build_passbook_entry(
        member_label="Ananya",
        age_band="6_11",
        debit_ug=90.0,
    )
    assert entry.budget_ug == 180.0
    assert entry.debit_ug == 90.0
    assert entry.balance_ug == 90.0
    assert entry.is_over_budget is False
    assert entry.overspend_ratio == 0.5
    # Cigarette equiv: mean_conc = 90 / 12 = 7.5 ug/m3 -> 7.5 / 22 ~ 0.34
    assert pytest.approx(entry.cigarette_equivalent, rel=1e-2) == 0.34
    assert "Rough equivalence" in entry.cigarette_label


def test_build_passbook_entry_over_budget() -> None:
    entry = build_passbook_entry(
        member_label="Rajesh",
        age_band="31_41",
        debit_ug=2400.0,
    )
    assert entry.budget_ug == 240.0
    assert entry.balance_ug == -2160.0
    assert entry.is_over_budget is True
    assert entry.overspend_ratio == 10.0
    # Mean conc = 2400 / 16 = 150 ug/m3 -> 150 / 22 ~ 6.82 cigarettes
    assert pytest.approx(entry.cigarette_equivalent, rel=1e-2) == 6.82


@given(
    debit=st.floats(min_value=0.0, max_value=50000.0),
    age_band=st.sampled_from(["0_1", "3_6", "6_11", "31_41", "61_71"]),
)
@settings(max_examples=100, deadline=None)
def test_property_overspend_ratio_invariant(debit: float, age_band: str) -> None:
    entry = build_passbook_entry("Member", age_band, debit)
    expected_ratio = debit / entry.budget_ug
    assert pytest.approx(entry.overspend_ratio, rel=1e-4) == expected_ratio
    assert entry.balance_ug == entry.budget_ug - debit
