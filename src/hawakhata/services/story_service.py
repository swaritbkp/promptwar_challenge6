"""Service for demo profiles and reproducible story mode tours."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hawakhata.core.errors import NotFoundError

DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data"
_PROFILES_PATH = DATA_ROOT / "fixtures" / "profiles.json"
_STORY_PATH = DATA_ROOT / "story.v1.json"


def load_demo_profiles() -> dict[str, Any]:
    """Load pre-configured demo profiles from fixtures."""
    if not _PROFILES_PATH.exists():
        return {}
    with _PROFILES_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    result = data.get("profiles", {})
    if isinstance(result, dict):
        return result
    return {}


def load_story(story_id: str) -> dict[str, Any]:
    """Load story tour definition and steps for a specific demo narrative.

    Raises:
        NotFoundError: If the story_id is not present in data/story.v1.json.
    """
    if not _STORY_PATH.exists():
        raise NotFoundError(f"Story configuration file missing at {_STORY_PATH.name}")

    with _STORY_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)

    stories = payload.get("stories", {})
    if story_id not in stories:
        raise NotFoundError(f"Story narrative '{story_id}' not found in story catalogue")

    story_meta = stories[story_id]
    steps = payload.get("steps", [])

    return {
        "story_id": story_id,
        "profile_ref": story_meta.get("profile_ref", ""),
        "fixture": story_meta.get("fixture", ""),
        "clock_local": story_meta.get("clock_local", "08:00"),
        "steps": steps,
    }
