from __future__ import annotations

import pytest

from hawakhata.agent.prompts import (
    PromptMetadata,
    PromptTemplate,
    _BoundedPromptCache,
    _parse_front_matter,
    clear_prompt_cache,
    list_prompts,
    load_prompt,
    render_prompt,
)


def test_load_prompt_agent_system() -> None:
    p = load_prompt("agent_system", version="v1.0")
    assert isinstance(p, PromptTemplate)
    assert isinstance(p.metadata, PromptMetadata)
    assert p.metadata.name == "agent_system"
    assert p.metadata.version == "v1.0"
    assert "System instruction" in p.metadata.purpose
    assert "{{LANGUAGE}}" in p.raw_body
    assert "{{CANARY}}" in p.raw_body


def test_load_prompt_narrator_and_planner() -> None:
    narrator = load_prompt("narrator", version="v1.0")
    assert narrator.metadata.name == "narrator"
    assert "{{RESULT_JSON}}" in narrator.raw_body

    planner = load_prompt("planner", version="v1.0")
    assert planner.metadata.name == "planner"
    assert "{{USER_TEXT}}" in planner.raw_body


def test_render_prompt_substitution() -> None:
    rendered = render_prompt(
        "narrator",
        version="v1.0",
        LANGUAGE="English",
        RESULT_JSON='{"pm25": 120}',
    )
    assert "{{LANGUAGE}}" not in rendered
    assert "language: English" in rendered
    assert '{"pm25": 120}' in rendered


def test_render_missing_placeholder_raises() -> None:
    template = load_prompt("narrator", version="v1.0")
    with pytest.raises(ValueError, match="Missing required placeholders"):
        template.render(LANGUAGE="Hindi")  # Missing RESULT_JSON


def test_load_prompt_nonexistent_raises() -> None:
    with pytest.raises(FileNotFoundError, match="Prompt not found"):
        load_prompt("nonexistent_prompt", version="v1.0")


def test_list_prompts() -> None:
    prompts = list_prompts("v1.0")
    assert len(prompts) >= 3
    names = {p.name for p in prompts}
    assert {"agent_system", "narrator", "planner"}.issubset(names)


def test_prompt_cache_clear() -> None:
    clear_prompt_cache()
    p1 = load_prompt("narrator", version="v1.0")
    p2 = load_prompt("narrator", version="v1.0")
    assert p1 is p2
    clear_prompt_cache()


def test_bounded_prompt_cache_eviction_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _BoundedPromptCache(max_entries=2, ttl_s=10.0)
    p = load_prompt("narrator", version="v1.0")
    cache.set("k1", p)
    cache.set("k2", p)
    assert cache.get("k1") is p

    # Exceed capacity: k1 will be evicted as oldest
    cache.set("k3", p)
    assert cache.get("k1") is None
    assert cache.get("k2") is p
    assert cache.get("k3") is p

    # Test expiry
    current_time = 100.0
    monkeypatch.setattr("time.monotonic", lambda: current_time)
    cache.set("k4", p)
    assert cache.get("k4") is p
    current_time += 15.0  # past 10s ttl
    assert cache.get("k4") is None


def test_list_prompts_empty_or_nonexistent() -> None:
    assert list_prompts("nonexistent_v999") == []


def test_parse_front_matter_no_dashes() -> None:
    meta, body = _parse_front_matter("Just plain text with no front matter.")
    assert meta.name == ""
    assert body == "Just plain text with no front matter."
