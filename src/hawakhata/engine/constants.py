"""Load and provide verified air quality and exposure science constants.

All physical, physiological, and emission constants are loaded from
`data/constants.v1.json` into typed, frozen value objects.
"""

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
    """A verified scientific constant with metadata and source citations.

    Attributes:
        id: Unique identifier matching data/constants.v1.json.
        value: Numeric value, list of breakpoints, or sub-dictionary.
        unit: Measurement unit (e.g. ug_m3, per_h, m3_per_day).
        range: Uncertainty range [low, high] or mapping of ranges.
        source: Primary literature, WHO, EPA, or CPCB citation.
        verified: Whether this parameter is verified against primary literature.
        applies_to: Optional geographic constraint.
    """

    id: str
    value: Any
    unit: str
    range: Any
    source: str
    verified: bool
    applies_to: str | None = None


@lru_cache(maxsize=4)
def load_constants(path: Path | None = None) -> dict[str, ConstantValue]:
    """Load and validate all constants from data/constants.v1.json.

    Args:
        path: Optional explicit file path for testing.

    Returns:
        Mapping of constant ID to ConstantValue object.

    Raises:
        ValidationFailed: If the file is missing, corrupt, or invalid schema.
    """
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
    """Retrieve a verified constant by ID.

    Args:
        constant_id: The ID of the constant in constants.v1.json.

    Returns:
        The verified ConstantValue object.

    Raises:
        KeyError: If the constant ID does not exist.
    """
    constants = load_constants()
    if constant_id not in constants:
        raise KeyError(f"Unknown constant id: '{constant_id}'")
    return constants[constant_id]
