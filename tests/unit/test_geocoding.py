"""Open-Meteo Geocoding proxy: India filter, cache, breaker and built-in fallback."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from hawakhata.config import Settings
from hawakhata.core.cache import TTLCache
from hawakhata.integrations.air_quality import CircuitBreaker
from hawakhata.integrations.geocoding import (
    GeocodingClient,
    builtin_city_matches,
    parse_geocoding_results,
)

PAYLOAD: dict[str, Any] = {
    "results": [
        {
            "name": "Jaipur",
            "latitude": 26.91962,
            "longitude": 75.78781,
            "country_code": "IN",
            "admin1": "Rajasthan",
        },
        {
            "name": "Jaipur",
            "latitude": 10.0,
            "longitude": 10.0,
            "country_code": "NG",
            "admin1": "X",
        },
        {
            "name": "Jaipur",
            "latitude": 27.26192,
            "longitude": 95.39595,
            "country_code": "IN",
            "admin1": "Assam",
        },
    ]
}


def test_parse_keeps_only_indian_places_and_rounds() -> None:
    places = parse_geocoding_results(PAYLOAD)
    assert [p.admin1 for p in places] == ["Rajasthan", "Assam"]
    assert places[0].lat == 26.9196 and places[0].source == "open_meteo_geocoding"
    assert parse_geocoding_results({}) == []


def test_builtin_matches_name_and_state() -> None:
    assert builtin_city_matches("luck")[0].name == "Lucknow"
    assert {p.name for p in builtin_city_matches("maharashtra")} == {"Mumbai", "Pune"}
    assert builtin_city_matches("zzzz") == []


def _client(handler: Any, app_env: str = "dev") -> GeocodingClient:
    return GeocodingClient(
        Settings(_env_file=None, app_env=app_env),
        TTLCache(max_entries=32, default_ttl_s=60),
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        breaker=CircuitBreaker(failure_threshold=1),
    )


@pytest.mark.asyncio
async def test_live_search_filters_to_india_and_caches() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=PAYLOAD)

    client = _client(handler)
    first = await client.search("  Jaipur ")
    second = await client.search("jaipur")
    assert len(first) == 2 and first == second and len(calls) == 1
    assert calls[0].url.params["countryCode"] == "IN" and calls[0].url.params["name"] == "Jaipur"


@pytest.mark.asyncio
async def test_failure_falls_back_to_builtin_list() -> None:
    client = _client(lambda _r: httpx.Response(503))
    places = await client.search("Patna")
    assert places and places[0].name == "Patna" and places[0].source == "builtin"


@pytest.mark.asyncio
async def test_test_env_uses_builtin_without_network() -> None:
    def boom(_r: httpx.Request) -> httpx.Response:
        raise AssertionError("network call in app_env=test")

    places = await _client(boom, app_env="test").search("Pune")
    assert places[0].name == "Pune" and places[0].source == "builtin"
