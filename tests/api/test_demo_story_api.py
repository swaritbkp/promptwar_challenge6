from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from hawakhata.core.errors import NotFoundError
from hawakhata.services import story_service


def test_get_demo_profiles(client: TestClient) -> None:
    resp = client.get("/api/v1/demo/profiles")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "meta" in body
    profiles = body["data"]
    assert "demo_ncr" in profiles
    assert "demo_chd" in profiles
    assert profiles["demo_ncr"]["display_name"]
    assert len(profiles["demo_ncr"]["members"]) > 0


def test_get_story_ncr_and_repeatability(client: TestClient) -> None:
    resp1 = client.get("/api/v1/story/ncr")
    assert resp1.status_code == 200
    s1 = resp1.json()
    assert s1["data"]["story_id"] == "ncr"
    assert s1["data"]["profile_ref"] == "demo_ncr"
    assert "steps" in s1["data"]
    assert len(s1["data"]["steps"]) > 0

    resp2 = client.get("/api/v1/story/ncr")
    assert resp2.status_code == 200
    s2 = resp2.json()
    assert s1["data"] == s2["data"]


def test_get_story_chd(client: TestClient) -> None:
    resp = client.get("/api/v1/story/chd")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["story_id"] == "chd"
    assert data["profile_ref"] == "demo_chd"


def test_get_unknown_story_404(client: TestClient) -> None:
    resp = client.get("/api/v1/story/nonexistent_story_id")
    assert resp.status_code == 404
    err = resp.json()
    assert "error" in err
    assert err["error"]["code"] == "NOT_FOUND"


def test_story_service_missing_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(story_service, "_PROFILES_PATH", pathlib.Path("/nonexistent/profiles.json"))
    assert story_service.load_demo_profiles() == {}

    monkeypatch.setattr(story_service, "_STORY_PATH", pathlib.Path("/nonexistent/story.json"))
    with pytest.raises(NotFoundError, match="Story configuration file missing"):
        story_service.load_story("ncr")
