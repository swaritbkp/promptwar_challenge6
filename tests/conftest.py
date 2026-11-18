from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hawakhata.app import create_app
from hawakhata.config import Settings


class FakeClock:
    """Manually advanced monotonic clock for deterministic time-based tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", rate_limit_per_min=5, max_body_bytes=2048)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def sample_profile_data() -> dict[str, Any]:
    return {
        "id": "fam_delhi",
        "name": "Delhi Household",
        "location": {"lat": 28.46, "lng": 77.03},
        "rooms": [{"name": "Living Room", "volume_m3": 50.0}],
        "sources": [],
        "members": [
            {
                "id": "m1",
                "name": "Arjun",
                "age_band": "adult",
                "sensitivities": ["asthma"],
                "schedule_blocks": [
                    {
                        "start_hour": 7,
                        "end_hour": 8,
                        "micro_env": "outdoor",
                        "activity": "walk",
                        "flexible": True,
                        "earliest_start": 6,
                        "latest_end": 18,
                    }
                ],
            }
        ],
    }
