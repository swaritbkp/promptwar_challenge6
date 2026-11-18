"""Provenance and explainability object for deterministic calculations.

Every displayed number in HawaKhata carries an Explanation citing the formula,
inputs, primary sources, constants used, and physical assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Explanation:
    """Provenance and explainability container for computed values.

    Attributes:
        formula: Plain-text or LaTeX-style mathematical expression used.
        inputs: Mapping of parameter name to formatted input value with units.
        constants_used: List of constant IDs from data/constants.v1.json.
        sources: Primary literature or regulatory citations.
        assumptions: Contextual modeling assumptions.
    """

    formula: str
    inputs: dict[str, Any]
    constants_used: list[str]
    sources: list[str]
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert the explanation into a clean JSON-serializable dictionary.

        Returns:
            Dictionary containing formula, inputs, constants, sources, and assumptions.
        """
        return {
            "formula": self.formula,
            "inputs": dict(self.inputs),
            "constants_used": list(self.constants_used),
            "sources": list(self.sources),
            "assumptions": list(self.assumptions),
        }
