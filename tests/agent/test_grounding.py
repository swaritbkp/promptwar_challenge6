from __future__ import annotations

from hawakhata.agent.grounding import (
    GroundingResult,
    check_numeric_grounding,
    collect_allowed_numbers,
    extract_numbers,
)


def test_extract_numbers_formats() -> None:
    text = (
        "Values: 1,234.5 and Indian 1,23,456 with 15.5% reduction, "
        "5x speed, 19\u00d7 multiplier, Devanagari \u0967\u096b\u0966."
    )
    extracted = extract_numbers(text)
    vals = [n.value for n in extracted]
    assert 1234.5 in vals
    assert 123456.0 in vals
    assert 15.5 in vals
    assert 5.0 in vals
    assert 19.0 in vals
    assert 150.0 in vals


def test_extract_numbers_skips_clock_and_years() -> None:
    text = "Meet at 14:00 on 2026-01-15 for 45 minutes."
    extracted = extract_numbers(text)
    vals = [n.value for n in extracted]
    assert 14.0 not in vals
    assert 2026.0 not in vals
    assert 45.0 in vals


def test_collect_allowed_numbers_rounding_and_percents() -> None:
    tool_output = {
        "pm25": 142.2,
        "fraction_clean": 0.35,
        "details": [{"cadr": 250.0}],
        "set_data": {12.0, 45.0},
    }
    allowed = collect_allowed_numbers(tool_output, user_text="My budget is 180 ug")
    # Exact
    assert any(abs(142.2 - a) < 1e-2 for a in allowed)
    # Rounded variants
    assert any(abs(142.0 - a) < 1e-2 for a in allowed)
    assert any(abs(140.0 - a) < 1e-2 for a in allowed)
    # Fraction to percent
    assert any(abs(35.0 - a) < 1e-2 for a in allowed)
    # User text
    assert any(abs(180.0 - a) < 1e-2 for a in allowed)
    # Whitelist
    assert 24.0 in allowed and 5.0 in allowed and 0.0 in allowed


def test_check_numeric_grounding_pass() -> None:
    tool_output = {"hourly_pm25": [142.2], "savings_ug": 50.0}
    user_msg = "Can we walk at 15:00?"

    # Grounded reply with exact, rounded, and whitelist numbers
    reply = (
        "PM2.5 is 142 \u00b5g/m\u00b3. You will save 50 \u00b5g "
        "over 24 hours (approx 3 cigarettes)."
    )
    res = check_numeric_grounding(reply, tool_output, user_text=user_msg)
    assert isinstance(res, GroundingResult)
    assert res.passed is True
    assert len(res.violations) == 0


def test_check_numeric_grounding_devanagari_pass() -> None:
    tool_output = {"hourly_pm25": [150.0]}
    reply = "आज वायु प्रदूषण का स्तर १५० माइक्रोग्राम है।"
    res = check_numeric_grounding(reply, tool_output)
    assert res.passed is True


def test_check_numeric_grounding_hallucination_fails() -> None:
    tool_output = {"hourly_pm25": [142.2]}
    # 789 is completely ungrounded
    reply = "The current pollution level is 789 ug/m3, which is critical."
    res = check_numeric_grounding(reply, tool_output)
    assert res.passed is False
    assert len(res.violations) == 1
    assert res.violations[0].value == 789.0
