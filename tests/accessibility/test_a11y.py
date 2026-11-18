"""Static accessibility (a11y) and page rendering checks for templates."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

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
        c = t_file.read_text("utf-8")
        assert not re.search(r"\bon\w+\s*=", c), f"Inline handler in {t_file}"
        assert "<script>" not in c, f"Inline script in {t_file}"


def test_pages_and_static_assets(client: TestClient) -> None:
    r_idx = client.get("/")
    assert r_idx.status_code == 200 and "Content-Security-Policy" in r_idx.headers
    assert all(
        m in r_idx.text
        for m in [
            "<!DOCTYPE html>",
            'class="skip-link"',
            'id="tab-today"',
            'id="tab-plan"',
            'id="ask-drawer"',
        ]
    )

    r_hiw = client.get("/how-it-works")
    assert r_hiw.status_code == 200
    assert all(
        t in r_hiw.text
        for t in [
            "Gemini Proposes, Code Decides",
            "WHO 2021",
            "Berkeley Earth",
            "Inhalation Volume",
        ]
    )

    css = client.get("/static/css/app.css")
    assert css.status_code == 200 and "--bg: #F7F6F2;" in css.text
    js = client.get("/static/js/app.js")
    assert js.status_code == 200 and "HawaKhataApp" in js.text
    en = client.get("/static/i18n/en.json")
    assert en.status_code == 200 and "HawaKhata" in en.text
    hi = client.get("/static/i18n/hi.json")
    assert hi.status_code == 200 and "हवा खाता" in hi.text
