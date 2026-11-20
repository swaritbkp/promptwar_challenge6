"""Instrument-verify WCAG 2.1 AA contrast of the Light and Dark design tokens in app.css."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[2] / "static" / "css" / "app.css").read_text("utf-8")
AA_NORMAL_TEXT = 4.5
BANDS = ("good", "satisfactory", "moderate", "poor", "very-poor", "severe")
TEXT_PAIRS = [
    ("ink", "bg"),
    ("ink", "surface"),
    ("ink", "well"),
    ("muted", "bg"),
    ("muted", "surface"),
    ("muted", "well"),
    ("accent", "surface"),
    ("on-accent", "accent"),
    ("accent", "accent-bg"),
    ("debit", "debit-bg"),
    ("saved", "saved-bg"),
    ("warn", "warn-bg"),
    *[(f"aqi-{b}-fg", f"aqi-{b}-bg") for b in BANDS],
    *[(f"aqi-{b}-fg", "surface") for b in BANDS],
]


def _theme_tokens(selector: str) -> dict[str, str]:
    """Return {token: #hex} declared in the first CSS block with exactly this selector."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"theme block {selector!r} not found in app.css"
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b", match.group(1)))


def _luminance(hex_color: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 contrast ratio between two #RRGGBB colours."""
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


THEMES = {
    "light": _theme_tokens(':root,[data-theme="light"]'),
    "dark": _theme_tokens('[data-theme="dark"]'),
}


def test_contrast_ratio_reference_values() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


def test_no_automatic_prefers_color_scheme_override() -> None:
    """The explicit toggle (data-theme) is the single source of truth."""
    assert "prefers-color-scheme" not in CSS


@pytest.mark.parametrize("theme", sorted(THEMES))
@pytest.mark.parametrize(("fg", "bg"), TEXT_PAIRS)
def test_token_pair_meets_wcag_aa(theme: str, fg: str, bg: str) -> None:
    tokens = THEMES[theme]
    assert fg in tokens and bg in tokens, f"{theme}: missing --{fg} or --{bg}"
    ratio = contrast_ratio(tokens[fg], tokens[bg])
    assert ratio >= AA_NORMAL_TEXT, f"{theme}: --{fg} on --{bg} = {ratio:.2f}:1 < 4.5:1"
