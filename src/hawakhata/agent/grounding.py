"""Numeric grounding gate verifying LLM claims against engine and API outputs.

Enforces the non-negotiable rule 'Gemini proposes, code decides' by ensuring
every quantitative claim originated from tool outputs, user inputs, or whitelist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEVANAGARI_DIGITS = {
    "\u0966": "0",
    "\u0967": "1",
    "\u0968": "2",
    "\u0969": "3",
    "\u096a": "4",
    "\u096b": "5",
    "\u096c": "6",
    "\u096d": "7",
    "\u096e": "8",
    "\u096f": "9",
}

ROUND_STEP_THRESHOLD = 50.0
PERCENT_BASE = 100.0

WHITELIST_NUMBERS: frozenset[float] = frozenset(
    {
        0.0,
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
        7.0,
        8.0,
        9.0,
        10.0,
        15.0,  # WHO 24h PM2.5 guideline
        22.0,  # Berkeley Earth cigarette equiv
        24.0,  # Hours in day
        48.0,  # 48h forecast
        60.0,  # Minutes in hour
        72.0,  # 72h forecast
        96.0,  # 96h forecast
        100.0,  # Percentage base
    }
)


@dataclass(frozen=True, slots=True)
class ExtractedNumber:
    """A numerical token extracted from text with source coordinate spans."""

    value: float
    raw: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class GroundingViolation:
    """An ungrounded or fabricated number identified in model text."""

    value: float
    raw: str
    start: int
    end: int
    reason: str


@dataclass(frozen=True, slots=True)
class GroundingResult:
    """Outcome of numeric grounding verification."""

    passed: bool
    violations: list[GroundingViolation]


def _translate_devanagari(text: str) -> str:
    """Translate Devanagari numerals to standard ASCII Arabic digits."""
    return "".join(DEVANAGARI_DIGITS.get(ch, ch) for ch in text)


def extract_numbers(text: str) -> list[ExtractedNumber]:
    """Extract all numbers (Western, Indian grouping, percentages, multipliers, Devanagari)."""
    translated = _translate_devanagari(text)
    skip_spans: list[tuple[int, int]] = []

    # 1. Skip clock times HH:MM
    for m in re.finditer(r"\b\d{1,2}:\d{2}\b", translated):
        skip_spans.append((m.start(), m.end()))

    # 2. Skip ISO dates and calendar years 2000..2099
    for m in re.finditer(r"\b20\d{2}\b", translated):
        skip_spans.append((m.start(), m.end()))

    # 3. Match candidate numbers (including commas, decimals, %, x/\u00d7)
    pattern = (
        r"(?<![A-Za-z0-9_])(?:\d{1,3}(?:,\d{2,3})+|\d+)"
        r"(?:\.\d+)?(?:%|[x\u00d7])?(?![A-Za-z0-9_])"
    )
    extracted: list[ExtractedNumber] = []

    for m in re.finditer(pattern, translated):
        start, end = m.start(), m.end()
        if any(s <= start and end <= e for s, e in skip_spans):
            continue

        raw_match = m.group(0)
        clean = raw_match.replace(",", "").rstrip("%x\u00d7")
        try:
            val = float(clean)
            extracted.append(
                ExtractedNumber(
                    value=val,
                    raw=text[start:end],
                    start=start,
                    end=end,
                )
            )
        except ValueError:
            continue

    return extracted


def collect_allowed_numbers(tool_outputs: object, user_text: str = "") -> set[float]:
    """Traverse tool outputs, user prompt, and whitelist to collect all ground-truth numbers."""
    allowed: set[float] = set(WHITELIST_NUMBERS)

    def _walk(obj: object) -> None:
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            v = float(obj)
            allowed.add(round(v, 4))
            allowed.add(round(v, 0))
            allowed.add(round(v, 1))
            allowed.add(round(v, 2))
            if v >= ROUND_STEP_THRESHOLD:
                allowed.add(round(v / 5.0) * 5.0)
                allowed.add(round(v / 10.0) * 10.0)
            if 0.0 <= v <= 1.0:
                allowed.add(round(v * PERCENT_BASE, 1))
                allowed.add(round(v * PERCENT_BASE, 0))
            if 0.0 <= v <= PERCENT_BASE:
                allowed.add(round(v / PERCENT_BASE, 2))
                allowed.add(round(v / PERCENT_BASE, 3))
        elif isinstance(obj, dict):
            for val in obj.values():
                _walk(val)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item)

    _walk(tool_outputs)

    if user_text:
        for num in extract_numbers(user_text):
            allowed.add(round(num.value, 4))
            allowed.add(round(num.value, 0))
            allowed.add(round(num.value, 1))

    return allowed


def check_numeric_grounding(
    reply: str,
    tool_outputs: object,
    user_text: str = "",
    tolerance: float = 1e-2,
) -> GroundingResult:
    """Verify that every number in the agent reply is grounded in allowed sources."""
    allowed = collect_allowed_numbers(tool_outputs, user_text)
    extracted = extract_numbers(reply)
    violations: list[GroundingViolation] = []

    for num in extracted:
        is_grounded = any(abs(num.value - a) <= tolerance for a in allowed)
        if not is_grounded:
            violations.append(
                GroundingViolation(
                    value=num.value,
                    raw=num.raw,
                    start=num.start,
                    end=num.end,
                    reason=f"Ungrounded number '{num.raw}' ({num.value}) not in allowed set",
                )
            )

    return GroundingResult(passed=len(violations) == 0, violations=violations)
