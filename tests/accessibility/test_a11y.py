"""Static accessibility (a11y) checks for templates and UI design contracts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_base_template_has_skip_link_and_landmarks() -> None:
    base = (ROOT / "templates" / "base.html").read_text("utf-8")
    req = [
        '<a href="#main-content" class="skip-link">',
        '<main id="main-content"',
        'aria-live="polite"',
        'id="a11y-announcer"',
        'role="status"',
    ]
    assert all(r in base for r in req)


def test_index_template_has_accessible_tabs_and_dialogs() -> None:
    index = (ROOT / "templates" / "index.html").read_text("utf-8")
    req = [
        'aria-labelledby="today-heading"',
        'aria-labelledby="plan-heading"',
        'aria-labelledby="indoor-heading"',
        'aria-labelledby="swaps-heading"',
        'role="dialog"',
        'aria-modal="true"',
    ]
    assert all(r in index for r in req)


def test_no_inline_event_handlers_or_unsafe_scripts() -> None:
    for t_file in (ROOT / "templates").rglob("*.html"):
        content = t_file.read_text("utf-8")
        assert not re.search(r"\bon\w+\s*=", content), f"Inline event handler found in {t_file}"
        assert "<script>" not in content, f"Inline script tag found in {t_file}"
