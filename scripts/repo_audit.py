"""Repository quality audit: python scripts/repo_audit.py."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "htmlcov",
    "node_modules",
    "design_exports",
}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".jsonl",
    ".html",
    ".css",
    ".js",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".example",
    ".cfg",
    ".ini",
    "",
}
JUNK_NAMES = {".env", ".coverage", ".digest.txt"}
MAX_FILE_BYTES = 150_000
MAX_FIXTURE_BYTES = 40_000
MAX_DIGEST_CHARS = 900_000

BANNED: list[tuple[str, str]] = [
    (r"\bos\.(getenv|environ)\b", "env access outside config.py"),
    (r"\b(TODO|FIXME|XXX)\b", "unfinished-work marker"),
    (r"^\s*print\(", "print() in application code"),
    (r"\b(temperature|top_p|top_k)\s*=", "deprecated Gemini sampling parameter"),
    (r"^\s*except\s*:", "bare except"),
    (r"\bNotImplementedError\b", "stub implementation"),
]
BANNED_JS: list[tuple[str, str]] = [
    (
        r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML\(",
        "HTML injection sink (use textContent / DOM APIs)",
    ),
    (r"\beval\(|new Function\(", "dynamic code execution"),
    (r"\bconsole\.log\(", "console.log left in UI code"),
    (r"https?://(cdn|unpkg|fonts)\.", "third-party CDN/font (breaks CSP, slows load)"),
]
UNFILLED_MARKER = "TO_BE_FILLED"
CITATION = re.compile(r"`([\w./-]+\.py):\s*([A-Za-z_][\w.]*)\(\)")


def _gitignore_patterns() -> list[str]:
    ignore = ROOT / ".gitignore"
    if not ignore.exists():
        return []
    lines = ignore.read_text(encoding="utf-8").splitlines()
    return [ln.strip().rstrip("/") for ln in lines if ln.strip() and not ln.startswith("#")]


def _matches(rel: str, pattern: str) -> bool:
    """Approximate gitignore matching: path patterns anchor at root, others match any part."""
    if "/" in pattern:
        return rel == pattern or rel.startswith(pattern + "/")
    return any(fnmatch.fnmatch(part, pattern) for part in rel.split("/"))


def is_ignored(rel: str, patterns: list[str]) -> bool:
    """Return True if ``rel`` is ignored, honouring ``!negation`` patterns."""
    ignored = False
    for pattern in patterns:
        if pattern.startswith("!"):
            if _matches(rel, pattern[1:]):
                ignored = False
        elif _matches(rel, pattern):
            ignored = True
    return ignored


def iter_files() -> list[Path]:
    """Return files that would be committed (git if available, else .gitignore-aware walk)."""
    if (ROOT / ".git").exists():
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode == 0:
            return sorted(ROOT / line for line in listed.stdout.splitlines() if line)
    patterns = _gitignore_patterns()
    files = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file() or any(part in SKIP_DIRS for part in rel.split("/")):
            continue
        if not is_ignored(rel, patterns):
            files.append(path)
    return sorted(files)


def persona_terms() -> set[str]:
    """Collect demo persona and place names that must never appear in src/ logic."""
    profiles = ROOT / "data" / "fixtures" / "profiles.json"
    if not profiles.exists():
        return set()
    data = json.loads(profiles.read_text(encoding="utf-8"))
    words: set[str] = set()
    for profile in data.get("profiles", {}).values():
        texts = [profile.get("display_name", ""), profile.get("location", {}).get("label", "")]
        texts += [m.get("label", "") for m in profile.get("members", [])]
        for text in texts:
            words.update(w for w in re.findall(r"[A-Z][a-z]{3,}", text) if w != "Family")
    return words


def check_banned(files: list[Path]) -> list[str]:
    """Scan src/ for banned patterns and hardcoded persona names."""
    problems = []
    names = persona_terms()
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if not rel.startswith("src/") or path.suffix != ".py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, why in BANNED:
                if why.startswith("env") and rel.endswith("hawakhata/config.py"):
                    continue
                if re.search(pattern, line):
                    problems.append(f"{rel}:{lineno}: {why}")
            hits = [n for n in names if re.search(rf"\b{n}\b", line)]
            if hits:
                problems.append(f"{rel}:{lineno}: hardcoded demo name(s) {hits}")
    return problems


def check_frontend_and_docs(files: list[Path]) -> list[str]:
    """Flag unsafe browser code and documents that still contain unfilled template markers."""
    problems = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix == ".js" and rel.startswith("static/"):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                problems += [
                    f"{rel}:{lineno}: {why}" for pat, why in BANNED_JS if re.search(pat, line)
                ]
        is_doc = path.suffix in {".md", ".html"}
        if is_doc and UNFILLED_MARKER in path.read_text(encoding="utf-8"):
            problems.append(f"{rel}: contains {UNFILLED_MARKER} (unfinished document)")
    return problems


def check_hygiene(files: list[Path]) -> tuple[list[str], int]:
    """Flag junk, oversized files and return the approximate digest size."""
    problems, digest_chars = [], 0
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        size = path.stat().st_size
        if path.name in JUNK_NAMES or path.suffix in {".pyc", ".log", ".sqlite", ".db"}:
            problems.append(f"{rel}: should not be committed")
        if rel.startswith("data/fixtures/") and size > MAX_FIXTURE_BYTES:
            problems.append(f"{rel}: fixture {size} B > {MAX_FIXTURE_BYTES} B")
        elif size > MAX_FILE_BYTES:
            problems.append(f"{rel}: {size} B > {MAX_FILE_BYTES} B")
        if path.suffix in TEXT_SUFFIXES:
            digest_chars += size
    if digest_chars > MAX_DIGEST_CHARS:
        problems.append(f"digest ~{digest_chars} chars > {MAX_DIGEST_CHARS}: trim the repo")
    return problems, digest_chars


def defined_names(py_file: Path) -> set[str]:
    """Return function/method/class names defined anywhere in a Python file."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def check_code_map() -> tuple[list[str], int]:
    """Verify every `path.py: name()` citation in README.md exists."""
    readme = ROOT / "README.md"
    if not readme.exists():
        return [], 0
    problems, count = [], 0
    for rel, name in CITATION.findall(readme.read_text(encoding="utf-8")):
        count += 1
        candidates = [ROOT / rel, ROOT / "src" / "hawakhata" / rel]
        target = next((c for c in candidates if c.exists()), None)
        if target is None:
            problems.append(f"README cites missing file {rel}")
        elif name.split(".")[-1] not in defined_names(target):
            problems.append(f"README cites {rel}: {name}() which does not exist")
    return problems, count


def main() -> int:
    """Run all checks and print a report; exit 1 if anything fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", action="store_true", help="write .digest.txt")
    args = parser.parse_args()
    files = iter_files()
    banned = check_banned(files)
    hygiene, digest_chars = check_hygiene(files)
    code_map, citations = check_code_map()
    if args.digest:
        parts = [
            f"===== {f.relative_to(ROOT).as_posix()} =====\n{f.read_text('utf-8', 'ignore')}"
            for f in files
            if f.suffix in TEXT_SUFFIXES and f.name not in JUNK_NAMES
        ]
        (ROOT / ".digest.txt").write_text("\n".join(parts), encoding="utf-8")
    frontend_docs = check_frontend_and_docs(files)
    problems = banned + frontend_docs + hygiene + code_map
    print(f"files={len(files)} digest_chars~{digest_chars} readme_citations={citations}")
    for problem in problems:
        print("FAIL", problem)
    print("AUDIT:", "CLEAN" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
