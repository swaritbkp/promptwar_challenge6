"""Swap service orchestrating sustainable alternatives and community Mohalla scaling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hawakhata.api.schemas import SwapsImpactRequest
from hawakhata.engine.swaps import (
    evaluate_swap,
    get_available_swaps,
    scale_to_community,
)


@dataclass(frozen=True, slots=True)
class SwapImpactEvaluation:
    """Consolidated assessment of household and community-scale swap impacts.

    Attributes:
        household: Single household multi-horizon emission and dose savings.
        community: Scaled community impact across residential mohalla/sector.
    """

    household: dict[str, Any]
    community: dict[str, Any]


def list_available_swaps() -> list[dict[str, Any]]:
    """Retrieve the curated catalogue of sustainable alternatives."""
    return get_available_swaps()


def compute_swap_impact(
    req: SwapsImpactRequest,
    outdoor_pm25_mean: float = 150.0,
) -> SwapImpactEvaluation:
    """Evaluate lifestyle swap deltas for household and scale to residential community.

    Args:
        req: Validated swap request containing swap_id, units, and scaling parameters.
        outdoor_pm25_mean: Mean ambient PM2.5 concentration for transit/exposure savings.

    Returns:
        SwapImpactEvaluation with household and scaled community deltas.
    """
    household_swap = evaluate_swap(
        swap_id=req.swap_id,
        units_per_day=req.units_per_day,
        days_per_week=req.days_per_week,
        outdoor_pm25_mean=outdoor_pm25_mean,
    )

    community_impact = scale_to_community(
        swap_result=household_swap,
        households=req.households,
        participation_rate=req.participation_rate,
    )

    return SwapImpactEvaluation(
        household=asdict(household_swap),
        community=asdict(community_impact),
    )
