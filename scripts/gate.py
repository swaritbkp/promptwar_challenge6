"""Cross-platform quality gate (Windows, macOS, Linux): python scripts/gate.py.

Runs lint, format check, strict typing, tests with coverage, the repo audit and,
when present, the eval harness. Exits non-zero on the first failing step so the
Antigravity agent (and you) get one unambiguous green/red answer.
"""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

STEPS: list[tuple[str, list[str]]] = [
    ("ruff lint", [PY, "-m", "ruff", "check", "."]),
    ("ruff format", [PY, "-m", "ruff", "format", "--check", "."]),
    ("mypy strict", [PY, "-m", "mypy", "--strict", "src"]),
    (
        "pytest + coverage",
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "--cov=src/hawakhata",
            "--cov-report=term-missing:skip-covered",
            "--cov-fail-under=90",
        ],
    ),
    ("repo audit", [PY, "scripts/repo_audit.py"]),
]


def _online(host: str = "pypi.org") -> bool:
    """Return True when the package index is reachable (pip-audit needs it)."""
    try:
        socket.create_connection((host, 443), timeout=3).close()
    except OSError:
        return False
    return True


def main() -> int:
    """Run each step in order; print a summary table; return the exit code."""
    steps = list(STEPS)
    if importlib.util.find_spec("bandit"):
        steps.append(("bandit SAST", [PY, "-m", "bandit", "-r", "src", "-ll", "-q"]))
    if (ROOT / "requirements.txt").exists() and importlib.util.find_spec("pip_audit"):
        # Needs network (PyPI/OSV): offline runs mark it SKIP instead of failing the gate.
        steps.append(("dependency audit", [PY, "-m", "pip_audit", "-r", "requirements.txt"]))
    if (ROOT / "eval" / "run_eval.py").exists():
        steps.append(("eval harness (fake LLM)", [PY, "eval/run_eval.py", "--mode", "fake"]))
    results: list[tuple[str, str, float]] = []
    for name, cmd in steps:
        print(f"\n=== {name} ===", flush=True)
        if name == "dependency audit" and not _online():
            print("offline: skipping pip-audit (CI runs it)")
            results.append((name, "SKIP", 0.0))
            continue
        started = time.perf_counter()
        ok = subprocess.run(cmd, cwd=ROOT, check=False).returncode == 0
        results.append((name, "PASS" if ok else "FAIL", time.perf_counter() - started))
        if not ok:
            break
    print("\n" + "-" * 48)
    for name, status, seconds in results:
        print(f"{status}  {name:<28} {seconds:6.1f}s")
    all_green = len(results) == len(steps) and all(st != "FAIL" for _, st, _ in results)
    print("GATE:", "GREEN" if all_green else "RED")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
