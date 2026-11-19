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
        assert 'style="' not in c, f"Inline style attribute in {t_file} (CSP violation)"


def test_pages_and_static_assets(client: TestClient) -> None:
    r_idx = client.get("/")
    assert r_idx.status_code == 200
    csp = r_idx.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp and "style-src 'self'" in csp and "unsafe-inline" not in csp

    for href in re.findall(
        r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']', r_idx.text
    ):
        r_css = client.get(href)
        assert (
            r_css.status_code == 200
            and "text/css" in r_css.headers.get("content-type", "")
            and len(r_css.text) > 1000
        )

    for src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', r_idx.text):
        r_js = client.get(src)
        assert (
            r_js.status_code == 200
            and "javascript" in r_js.headers.get("content-type", "")
            and len(r_js.text) > 500
        )

    r_hiw = client.get("/how-it-works")
    assert r_hiw.status_code == 200 and all(
        t in r_hiw.text
        for t in [
            "Gemini Proposes, Code Decides",
            "WHO 2021",
            "Berkeley Earth",
            "Inhalation Volume",
        ]
    )
