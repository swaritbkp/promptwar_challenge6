"""Load and provide verified air quality and exposure science constants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from hawakhata.core.errors import ValidationFailedError

DEFAULT_CONSTANTS_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "constants.v1.json"
)


@dataclass(frozen=True, slots=True)
class ConstantValue:
    """A verified scientific constant with metadata and source citations."""

    id: str
    value: Any
    unit: str
    range: Any
    source: str
    verified: bool
    applies_to: str | None = None


@lru_cache(maxsize=4)
def load_constants(path: Path | None = None) -> dict[str, ConstantValue]:
    """Load and validate all constants from data/constants.v1.json."""
    target_path = path or DEFAULT_CONSTANTS_PATH
    if not target_path.exists():
        raise ValidationFailedError(f"Constants file not found at {target_path}")

    try:
        with target_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise ValidationFailedError(f"Failed to parse constants JSON: {exc}") from exc

    if "constants" not in data or not isinstance(data["constants"], dict):
        raise ValidationFailedError("Constants JSON must contain a root 'constants' mapping")

    result: dict[str, ConstantValue] = {}
    for cid, entry in data["constants"].items():
        if not isinstance(entry, dict) or "value" not in entry or "source" not in entry:
            raise ValidationFailedError(f"Constant '{cid}' has invalid schema")
        result[cid] = ConstantValue(
            id=cid,
            value=entry["value"],
            unit=entry.get("unit", ""),
            range=entry.get("range"),
            source=entry["source"],
            verified=bool(entry.get("verified", False)),
            applies_to=entry.get("applies_to"),
        )
    return result


def get_constant(constant_id: str) -> ConstantValue:
    """Retrieve a verified constant by ID."""
    constants = load_constants()
    if constant_id not in constants:
        raise KeyError(f"Unknown constant id: '{constant_id}'")
    return constants[constant_id]
