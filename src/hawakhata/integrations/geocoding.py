"""Server-side proxy for Open-Meteo Geocoding, limited to Indian places, with offline fallback.

The browser never calls Open-Meteo directly: the FastAPI route forwards a validated query
through the shared ``httpx.AsyncClient``. Results are cached (bounded TTL-LRU) and, when the
API is unreachable or ``app_env == "test"``, the built-in city list from data/cities.v1.json
answers instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

import httpx

from hawakhata.core.logging import get_logger
from hawakhata.engine.cities import get_supported_cities
from hawakhata.integrations.air_quality import CircuitBreaker

if TYPE_CHECKING:
    from hawakhata.config import Settings
    from hawakhata.core.cache import CacheBackend

logger = get_logger(__name__)
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEO_CACHE_TTL_S = 86_400


@dataclass(frozen=True, slots=True)
class GeoPlace:
    """One searchable Indian place."""

    name: str
    admin1: str
    lat: float
    lng: float
    source: str


def builtin_city_matches(query: str, limit: int = 8) -> list[GeoPlace]:
    """Case-insensitive substring match against the built-in Indian city list."""
    q = query.strip().lower()
    return [
        GeoPlace(c.name, c.state, c.lat, c.lng, "builtin")
        for c in get_supported_cities()
        if q in c.name.lower() or q in c.state.lower()
    ][:limit]


def parse_geocoding_results(payload: dict[str, Any], limit: int = 8) -> list[GeoPlace]:
    """Keep only results inside India (country_code == "IN")."""
    out: list[GeoPlace] = []
    for r in payload.get("results") or []:
        if str(r.get("country_code", "")).upper() != "IN":
            continue
        out.append(
            GeoPlace(
                str(r.get("name", ""))[:120],
                str(r.get("admin1", ""))[:120],
                round(float(r["latitude"]), 4),
                round(float(r["longitude"]), 4),
                "open_meteo_geocoding",
            )
        )
    return out[:limit]


class GeocodingClient:
    """Open-Meteo Geocoding proxy with cache, circuit breaker, and built-in fallback."""

    def __init__(
        self,
        settings: Settings,
        cache: CacheBackend,
        http_client: httpx.AsyncClient,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings, self._cache, self._http = settings, cache, http_client
        self._breaker = breaker or CircuitBreaker()

    async def search(self, query: str, limit: int = 8) -> list[GeoPlace]:
        """Search Indian cities/towns by name; never raises, never calls out in tests."""
        q = " ".join(query.split())
        key = f"geo:search:{q.lower()}:{limit}"
        cached = await self._cache.get(key)
        if isinstance(cached, list):
            return [GeoPlace(**c) for c in cached if isinstance(c, dict)]

        places: list[GeoPlace] = []
        if self._settings.app_env != "test" and self._breaker.can_execute():
            try:
                resp = await self._http.get(
                    GEOCODING_URL,
                    params={
                        "name": q,
                        "count": 20,
                        "language": "en",
                        "format": "json",
                        "countryCode": "IN",
                    },
                    timeout=self._settings.aq_timeout_s,
                )
                resp.raise_for_status()
                places = parse_geocoding_results(resp.json(), limit)
                self._breaker.record_success()
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                logger.info("Geocoding failed, using built-in cities: %s", type(exc).__name__)
                self._breaker.record_failure()
        if not places:
            places = builtin_city_matches(q, limit)
        await self._cache.set(key, [asdict(p) for p in places], ttl_s=GEO_CACHE_TTL_S)
        return places
