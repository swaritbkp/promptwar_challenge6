"""Monte Carlo forecast uncertainty utilities."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from hawakhata.engine.explain import Explanation

DEFAULT_SPREAD = 0.25
DEFAULT_SAMPLE_COUNT = 200
DEFAULT_SEED = 42
AUTOCORRELATION_RHO = 0.7


@dataclass(frozen=True, slots=True)
class ForecastUncertaintyResult:
    """Percentile summary and sample paths for air quality forecast uncertainty."""

    base_series: list[float]
    p50_series: list[float]
    p90_series: list[float]
    sample_count: int
    seed: int
    explanation: Explanation


def sample_forecast_paths(
    base_series: list[float],
    spread: float = DEFAULT_SPREAD,
    n: int = DEFAULT_SAMPLE_COUNT,
    seed: int = DEFAULT_SEED,
) -> list[list[float]]:
    """Generate n temporally correlated forecast trajectories using seeded random sampling."""
    if not base_series or n <= 0:
        return []

    if spread <= 0.0:
        return [[max(0.0, float(c)) for c in base_series] for _ in range(n)]

    rng = random.Random(seed)  # noqa: S311 - seeded simulation RNG, not cryptographic security
    num_hours = len(base_series)
    rho = AUTOCORRELATION_RHO
    decorr_weight = math.sqrt(max(0.0, 1.0 - (rho * rho)))
    sigma = max(0.01, spread)
    bias_correction = 0.5 * (sigma * sigma)

    paths: list[list[float]] = []

    for _ in range(n):
        path: list[float] = []
        z = rng.gauss(0.0, 1.0)
        for h in range(num_hours):
            eps = rng.gauss(0.0, 1.0)
            z = (rho * z) + (decorr_weight * eps)
            multiplier = math.exp((sigma * z) - bias_correction)
            conc = max(0.0, base_series[h] * multiplier)
            path.append(round(conc, 2))
        paths.append(path)

    return paths


def p50_p90(samples: list[list[float]]) -> tuple[list[float], list[float]]:
    """Compute the 50th (median) and 90th percentile series from sample paths."""
    if not samples or not samples[0]:
        return [], []

    num_hours = len(samples[0])
    num_samples = len(samples)

    p50: list[float] = []
    p90: list[float] = []

    # 50th percentile rank index and 90th percentile rank index
    idx_50 = round(0.50 * (num_samples - 1))
    idx_90 = round(0.90 * (num_samples - 1))

    for h in range(num_hours):
        hour_vals = sorted(samples[i][h] for i in range(num_samples))
        p50.append(round(hour_vals[idx_50], 2))
        p90.append(round(hour_vals[idx_90], 2))

    return p50, p90


def compute_forecast_uncertainty(
    base_series: list[float],
    spread: float = DEFAULT_SPREAD,
    n: int = DEFAULT_SAMPLE_COUNT,
    seed: int = DEFAULT_SEED,
) -> ForecastUncertaintyResult:
    """Generate forecast samples and compute P50/P90 trajectories with explanation."""
    samples = sample_forecast_paths(base_series=base_series, spread=spread, n=n, seed=seed)
    p50, p90 = p50_p90(samples)

    exp = Explanation(
        formula="C_sample(t) = C_base(t) * exp(sigma * z(t) - 0.5 * sigma^2), "
        "z(t) = rho*z(t-1) + sqrt(1-rho^2)*eps(t)",
        inputs={
            "spread_sigma": f"{spread:.2f}",
            "sample_count": n,
            "seed": seed,
            "autocorrelation_rho": f"{AUTOCORRELATION_RHO:.2f}",
            "hours_forecast": len(base_series),
        },
        constants_used=[],
        sources=["Meteorological dispersion ensemble methods; log-normal pollution distribution"],
        assumptions=[
            "Log-normal multiplicative noise preserves concentration non-negativity",
            "AR(1) temporal autocorrelation models realistic multi-hour weather persistence",
        ],
    )

    return ForecastUncertaintyResult(
        base_series=[round(c, 2) for c in base_series],
        p50_series=p50,
        p90_series=p90,
        sample_count=n,
        seed=seed,
        explanation=exp,
    )
