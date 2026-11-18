"""Tests for web UI pages, templates and static assets."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_index_page_returns_200_and_contains_landmarks(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    text = resp.text
    req_markers = [
        "<!DOCTYPE html>",
        'class="skip-link"',
        'href="#main-content"',
        "<header",
        "<nav",
        "<main",
        'id="tab-today"',
        'id="tab-plan"',
        'id="tab-indoor"',
        'id="tab-swaps"',
        'id="ask-drawer"',
    ]
    assert all(m in text for m in req_markers)
    assert "Content-Security-Policy" in resp.headers


def test_how_it_works_page_renders_science_and_trust(client: TestClient) -> None:
    resp = client.get("/how-it-works")
    assert resp.status_code == 200 and "text/html" in resp.headers["content-type"]
    text = resp.text
    req_terms = ["Gemini Proposes, Code Decides", "WHO 2021", "Berkeley Earth", "Inhalation Volume"]
    assert all(t in text for t in req_terms)


def test_static_assets_serve_correctly(client: TestClient) -> None:
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "--bg: #F7F6F2;" in css.text

    js = client.get("/static/js/app.js")
    assert js.status_code == 200
    assert "HawaKhataApp" in js.text

    en = client.get("/static/i18n/en.json")
    assert en.status_code == 200
    assert "HawaKhata" in en.text

    hi = client.get("/static/i18n/hi.json")
    assert hi.status_code == 200
    assert "हवा खाता" in hi.text
