from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "repo_audit", Path(__file__).resolve().parents[2] / "scripts" / "repo_audit.py"
)
assert _SPEC is not None and _SPEC.loader is not None
repo_audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repo_audit)

PATTERNS = [".env", ".env.*", "!.env.example", "docs/internal", "__pycache__"]


@pytest.mark.parametrize(
    ("rel", "ignored"),
    [
        (".env", True),
        (".env.local", True),
        (".env.example", False),
        ("docs/internal/notes.md", True),
        ("docs/PRD.md", False),
        ("src/hawakhata/__pycache__/app.cpython-312.pyc", True),
    ],
)
def test_gitignore_matching(rel: str, ignored: bool) -> None:
    assert repo_audit.is_ignored(rel, PATTERNS) is ignored


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ("bubble.innerHTML = reply;", True),
        ("node.insertAdjacentHTML('beforeend', x)", True),
        ("bubble.textContent = reply;", False),
        ("eval(code)", True),
        ('<link href="https://fonts.googleapis.com/css">', True),
    ],
)
def test_frontend_sinks_are_detected(line: str, flagged: bool) -> None:
    hits = [why for pattern, why in repo_audit.BANNED_JS if re.search(pattern, line)]
    assert bool(hits) is flagged
