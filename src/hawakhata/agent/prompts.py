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
    """Bounded synchronous cache with TTL and FIFO eviction (Rule 1 compliant)."""

    def __init__(self, max_entries: int = 64, ttl_s: float = 3600.0) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
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
            oldest_key = next(iter(self._entries))
            self._entries.pop(oldest_key, None)
        self._entries[key] = _CacheEntry(value=value, expires_at=time.monotonic() + self.ttl_s)

    def clear(self) -> None:
        self._entries.clear()


_PROMPT_CACHE = _BoundedPromptCache(max_entries=64, ttl_s=3600.0)


@dataclass(frozen=True, slots=True)
class PromptMetadata:
    """Metadata extracted from YAML front-matter."""

    name: str
    version: str
    purpose: str


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Prompt template containing metadata and body with placeholder substitution."""

    metadata: PromptMetadata
    raw_body: str

    def required_placeholders(self) -> set[str]:
        """Return the set of uppercase placeholder keys required by this prompt."""
        return set(PLACEHOLDER_PATTERN.findall(self.raw_body))

    def render(self, **kwargs: object) -> str:
        """Render prompt text by replacing {{KEY}} placeholders with provided arguments."""
        missing = self.required_placeholders() - set(kwargs.keys())
        if missing:
            missing_sorted = sorted(missing)
            raise ValueError(f"Missing required placeholders: {missing_sorted}")

        rendered = self.raw_body
        for key, val in kwargs.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(val))
        return rendered


def _parse_front_matter(content: str) -> tuple[PromptMetadata, str]:
    """Extract YAML-like front-matter and markdown body."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return PromptMetadata(name="", version="", purpose=""), content

    fm_lines: list[str] = []
    body_idx = 0
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_idx = i + 1
            break
        fm_lines.append(line)

    meta_dict: dict[str, str] = {}
    for line in fm_lines:
        if ":" in line:
            k, v = line.split(":", 1)
            meta_dict[k.strip()] = v.strip()

    body = "\n".join(lines[body_idx:]).strip()
    meta = PromptMetadata(
        name=meta_dict.get("name", ""),
        version=meta_dict.get("version", ""),
        purpose=meta_dict.get("purpose", ""),
    )
    return meta, body


def load_prompt(
    name: str,
    version: str = PROMPT_VERSION,
    base_dir: Path | None = None,
) -> PromptTemplate:
    """Load a prompt template from disk with bounded TTL caching."""
    cache_key = f"{version}:{name}"
    cached = _PROMPT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    prompts_root = base_dir or PROMPTS_DIR
    target_path = prompts_root / version / f"{name}.md"
    if not target_path.exists():
        raise FileNotFoundError(f"Prompt not found: {target_path}")

    content = target_path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(content)
    template = PromptTemplate(metadata=meta, raw_body=body)
    _PROMPT_CACHE.set(cache_key, template)
    return template


def render_prompt(
    name: str,
    version: str = PROMPT_VERSION,
    base_dir: Path | None = None,
    **kwargs: object,
) -> str:
    """Convenience helper to load and render a prompt in one step."""
    template = load_prompt(name, version=version, base_dir=base_dir)
    return template.render(**kwargs)


def list_prompts(
    version: str = PROMPT_VERSION,
    base_dir: Path | None = None,
) -> list[PromptMetadata]:
    """Enumerate all available prompt metadata in a specific prompt version directory."""
    prompts_root = base_dir or PROMPTS_DIR
    v_dir = prompts_root / version
    if not v_dir.exists():
        return []

    results: list[PromptMetadata] = []
    for p in sorted(v_dir.glob("*.md")):
        content = p.read_text(encoding="utf-8")
        meta, _ = _parse_front_matter(content)
        if meta.name:
            results.append(meta)
    return results


def clear_prompt_cache() -> None:
    """Clear in-memory prompt cache for testing."""
    _PROMPT_CACHE.clear()
