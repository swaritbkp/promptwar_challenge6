from __future__ import annotations

import pytest

from hawakhata.engine.uncertainty import (
    compute_forecast_uncertainty,
    p50_p90,
    sample_forecast_paths,
)


def test_sample_forecast_paths_determinism() -> None:
    base = [120.0, 150.0, 180.0, 110.0]
    samples1 = sample_forecast_paths(base, spread=0.2, n=50, seed=42)
    samples2 = sample_forecast_paths(base, spread=0.2, n=50, seed=42)
    assert samples1 == samples2


def test_sample_forecast_different_seeds() -> None:
    base = [100.0] * 12
    samples1 = sample_forecast_paths(base, spread=0.2, n=50, seed=42)
    samples2 = sample_forecast_paths(base, spread=0.2, n=50, seed=99)
    assert samples1 != samples2


def test_zero_spread_returns_exact_base() -> None:
    base = [85.0, 95.0, 105.0]
    samples = sample_forecast_paths(base, spread=0.0, n=20, seed=42)
    for path in samples:
        for val, b in zip(path, base, strict=True):
            assert pytest.approx(val, rel=1e-5) == b


def test_p50_p90_invariants() -> None:
    base = [100.0, 200.0, 150.0]
    samples = sample_forecast_paths(base, spread=0.3, n=200, seed=42)
    p50, p90 = p50_p90(samples)

    assert len(p50) == 3
    assert len(p90) == 3
    for h in range(3):
        # 90th percentile must be greater than or equal to median
        assert p90[h] >= p50[h]
        # Concentrations are strictly positive
        assert p50[h] > 0
        assert p90[h] > 0


def test_empty_inputs_edge_cases() -> None:
    assert sample_forecast_paths([], n=10) == []
    assert sample_forecast_paths([100.0], n=0) == []
    assert p50_p90([]) == ([], [])
    assert p50_p90([[]]) == ([], [])


def test_compute_forecast_uncertainty_explanation() -> None:
    base = [150.0] * 24
    res = compute_forecast_uncertainty(base, spread=0.25, n=100, seed=42)
    assert res.sample_count == 100
    assert res.seed == 42
    assert len(res.p50_series) == 24
    assert len(res.p90_series) == 24
    assert res.explanation.formula != ""
