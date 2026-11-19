"""Versioned prompt registry with front-matter metadata and bounded caching."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from hawakhata.version import PROMPT_VERSION

ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROMPTS_DIR = ROOT / "prompts"
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: PromptTemplate
    expires_at: float


class _BoundedPromptCache:
    """Bounded synchronous cache with TTL and FIFO eviction."""

    def __init__(self, max_entries: int = 64, ttl_s: float = 3600.0) -> None:
        self.max_entries, self.ttl_s = max_entries, ttl_s
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> PromptTemplate | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: PromptTemplate) -> None:
        if len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)), None)
        self._entries[key] = _CacheEntry(value=value, expires_at=time.monotonic() + self.ttl_s)

    def clear(self) -> None:
        self._entries.clear()


_PROMPT_CACHE = _BoundedPromptCache()


@dataclass(frozen=True, slots=True)
class PromptMetadata:
    name: str
    version: str
    purpose: str


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    metadata: PromptMetadata
    raw_body: str

    def required_placeholders(self) -> set[str]:
        return set(PLACEHOLDER_PATTERN.findall(self.raw_body))

    def render(self, **kwargs: object) -> str:
        missing = self.required_placeholders() - set(kwargs.keys())
        if missing:
            raise ValueError(f"Missing required placeholders: {sorted(missing)}")
        res = self.raw_body
        for k, v in kwargs.items():
            res = res.replace(f"{{{{{k}}}}}", str(v))
        return res


def _parse_front_matter(content: str) -> tuple[PromptMetadata, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return PromptMetadata("", "", ""), content
    fm_lines, body_idx = [], 0
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_idx = i + 1
            break
        fm_lines.append(line)
    meta_dict = dict(line.split(":", 1) for line in fm_lines if ":" in line)
    clean_dict = {k.strip(): v.strip() for k, v in meta_dict.items()}
    return PromptMetadata(
        clean_dict.get("name", ""), clean_dict.get("version", ""), clean_dict.get("purpose", "")
    ), "\n".join(lines[body_idx:]).strip()


def load_prompt(
    name: str, version: str = PROMPT_VERSION, base_dir: Path | None = None
) -> PromptTemplate:
    cache_key = f"{version}:{name}"
    cached = _PROMPT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    p = (base_dir or PROMPTS_DIR) / version / f"{name}.md"
    if not p.exists():
        raise FileNotFoundError(f"Prompt not found: {p}")
    meta, body = _parse_front_matter(p.read_text("utf-8"))
    tmpl = PromptTemplate(meta, body)
    _PROMPT_CACHE.set(cache_key, tmpl)
    return tmpl


def render_prompt(
    name: str, version: str = PROMPT_VERSION, base_dir: Path | None = None, **kwargs: object
) -> str:
    return load_prompt(name, version=version, base_dir=base_dir).render(**kwargs)


def list_prompts(
    version: str = PROMPT_VERSION, base_dir: Path | None = None
) -> list[PromptMetadata]:
    v_dir = (base_dir or PROMPTS_DIR) / version
    if not v_dir.exists():
        return []
    res = []
    for p in sorted(v_dir.glob("*.md")):
        meta, _ = _parse_front_matter(p.read_text("utf-8"))
        if meta.name:
            res.append(meta)
    return res


def clear_prompt_cache() -> None:
    _PROMPT_CACHE.clear()
