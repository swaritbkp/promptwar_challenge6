"""Monte Carlo forecast uncertainty utilities."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from hawakhata.engine.explain import Explanation


@dataclass(frozen=True, slots=True)
class ForecastUncertaintyResult:
    base_series: list[float]
    p50_series: list[float]
    p90_series: list[float]
    sample_count: int
    seed: int
    explanation: Explanation


def sample_forecast_paths(
    base_series: list[float], spread: float = 0.25, n: int = 200, seed: int = 42
) -> list[list[float]]:
    """Generate n temporally correlated forecast trajectories using seeded random sampling."""
    if not base_series or n <= 0:
        return []
    if spread <= 0.0:
        return [[max(0.0, float(c)) for c in base_series] for _ in range(n)]

    rng = random.Random(seed)  # noqa: S311
    num_hours = len(base_series)
    rho = 0.7
    decorr = math.sqrt(max(0.0, 1.0 - (rho * rho)))
    sigma = max(0.01, spread)
    bias_corr = 0.5 * (sigma * sigma)

    paths: list[list[float]] = []
    for _ in range(n):
        path: list[float] = []
        z = rng.gauss(0.0, 1.0)
        for h in range(num_hours):
            eps = rng.gauss(0.0, 1.0)
            z = (rho * z) + (decorr * eps)
            multiplier = math.exp((sigma * z) - bias_corr)
            conc = max(0.0, base_series[h] * multiplier)
            path.append(round(conc, 2))
        paths.append(path)
    return paths


def p50_p90(samples: list[list[float]]) -> tuple[list[float], list[float]]:
    """Compute the 50th and 90th percentile series from sample paths."""
    if not samples or not samples[0]:
        return [], []
    num_hours, num_samples = len(samples[0]), len(samples)
    idx_50, idx_90 = round(0.50 * (num_samples - 1)), round(0.90 * (num_samples - 1))
    p50, p90 = [], []
    for h in range(num_hours):
        h_vals = sorted(samples[i][h] for i in range(num_samples))
        p50.append(round(h_vals[idx_50], 2))
        p90.append(round(h_vals[idx_90], 2))
    return p50, p90


def compute_forecast_uncertainty(
    base_series: list[float], spread: float = 0.25, n: int = 200, seed: int = 42
) -> ForecastUncertaintyResult:
    """Generate forecast samples and compute P50/P90 trajectories with explanation."""
    samples = sample_forecast_paths(base_series=base_series, spread=spread, n=n, seed=seed)
    p50, p90 = p50_p90(samples)
    exp = Explanation(
        formula="C_sample(t) = C_base(t) * exp(sigma * z(t) - 0.5 * sigma^2)",
        inputs={"spread_sigma": f"{spread:.2f}", "sample_count": n, "seed": seed},
        constants_used=[],
        sources=["Log-normal dispersion ensemble"],
        assumptions=["Multiplicative noise preserves non-negativity"],
    )
    return ForecastUncertaintyResult(
        base_series=[round(c, 2) for c in base_series],
        p50_series=p50,
        p90_series=p90,
        sample_count=n,
        seed=seed,
        explanation=exp,
    )
