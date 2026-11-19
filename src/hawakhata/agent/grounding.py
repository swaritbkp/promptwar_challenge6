"""Numeric grounding gate verifying LLM claims against engine and API outputs."""

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
        15.0,
        22.0,
        24.0,
        48.0,
        60.0,
        72.0,
        96.0,
        100.0,
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


def extract_numbers(text: str) -> list[ExtractedNumber]:
    """Extract all numbers (Western, Indian grouping, percentages, multipliers, Devanagari)."""
    translated = "".join(DEVANAGARI_DIGITS.get(ch, ch) for ch in text)
    skip_spans = [(m.start(), m.end()) for m in re.finditer(r"\b\d{1,2}:\d{2}\b", translated)]
    skip_spans += [(m.start(), m.end()) for m in re.finditer(r"\b20\d{2}\b", translated)]

    pattern = (
        r"(?<![A-Za-z0-9_])(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?:%|[x\u00d7])?(?![A-Za-z0-9_])"
    )
    extracted: list[ExtractedNumber] = []

    for m in re.finditer(pattern, translated):
        start, end = m.start(), m.end()
        if any(s <= start and end <= e for s, e in skip_spans):
            continue
        clean = m.group(0).replace(",", "").rstrip("%x\u00d7")
        try:
            extracted.append(
                ExtractedNumber(value=float(clean), raw=text[start:end], start=start, end=end)
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
            allowed.update({round(v, 4), round(v, 0), round(v, 1), round(v, 2)})
            if v >= 50.0:
                allowed.update({round(v / 5.0) * 5.0, round(v / 10.0) * 10.0})
            if 0.0 <= v <= 1.0:
                allowed.update({round(v * 100.0, 1), round(v * 100.0, 0)})
            if 0.0 <= v <= 100.0:
                allowed.update({round(v / 100.0, 2), round(v / 100.0, 3)})
        elif isinstance(obj, dict):
            for val in obj.values():
                _walk(val)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item)

    _walk(tool_outputs)
    if user_text:
        for num in extract_numbers(user_text):
            allowed.update({round(num.value, 4), round(num.value, 0), round(num.value, 1)})
    return allowed


def check_numeric_grounding(
    reply: str,
    tool_outputs: object,
    user_text: str = "",
    tolerance: float = 1e-2,
) -> GroundingResult:
    """Verify that every number in the agent reply is grounded in allowed sources."""
    allowed = collect_allowed_numbers(tool_outputs, user_text)
    violations = [
        GroundingViolation(
            num.value, num.raw, num.start, num.end, f"Ungrounded '{num.raw}' ({num.value})"
        )
        for num in extract_numbers(reply)
        if not any(abs(num.value - a) <= tolerance for a in allowed)
    ]
    return GroundingResult(passed=len(violations) == 0, violations=violations)
