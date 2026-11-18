"""Google Maps Platform Air Quality API client with caching, resilience, and fixture fallback."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

from hawakhata.core.logging import get_logger

if TYPE_CHECKING:
    from hawakhata.config import Settings
    from hawakhata.core.cache import CacheBackend

logger = get_logger(__name__)

DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "fixtures"
AQ_API_BASE = "https://airquality.googleapis.com/v1"
DELHI_NCR_COORDS = (28.4595, 77.0266)
CHANDIGARH_COORDS = (30.7333, 76.7794)
MIN_ISO_TIME_LEN: int = 16
HTTP_OK: int = 200
MAX_RETRY_ATTEMPTS: int = 2


def round_coordinates(lat: float, lng: float) -> tuple[float, float]:
    """Round coordinates to 2 decimal places (~1.1 km precision)."""
    return round(lat, 2), round(lng, 2)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great circle distance between two points in km."""
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2.0) ** 2
    )
    return radius_km * (2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))


class CircuitState(StrEnum):
    """Resilience circuit state."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """In-memory circuit breaker for external Google APIs."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_time_s: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialize circuit breaker with threshold and recovery time."""
        self._failure_threshold = failure_threshold
        self._recovery_time_s = recovery_time_s
        self._clock = clock or time.monotonic
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

    @property
    def state(self) -> CircuitState:
        """Current operational state."""
        if (
            self._state == CircuitState.OPEN
            and (self._clock() - self._last_failure_time) >= self._recovery_time_s
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def can_execute(self) -> bool:
        """Return True if requests are allowed through."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """Reset failures upon successful response."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Register a network failure or 5xx response."""
        self._failure_count += 1
        self._last_failure_time = self._clock()
        if self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning("AQ circuit breaker OPENED after %d failures", self._failure_count)


@dataclass(frozen=True, slots=True)
class HourlyAirPoint:
    """Normalised single-hour air quality observation."""

    time_utc: str
    time_local: str
    pm25_ug_m3: float
    pm10_ug_m3: float | None
    aqi_local: int | None
    aqi_universal: int | None
    category_local: str
    dominant_pollutant: str
    health_recs: dict[str, str]


@dataclass(frozen=True, slots=True)
class HourlyAirSeries:
    """Normalised multi-hour air quality forecast series."""

    points: list[HourlyAirPoint]
    location_cell: str
    data_mode: Literal["live", "fixture"]
    fetched_at: str


def _normalise_raw_forecast_point(raw: dict[str, Any]) -> HourlyAirPoint:
    """Transform Google Maps AQ forecast point into normalized HourlyAirPoint."""
    date_time = str(raw.get("dateTime", ""))
    indexes = raw.get("indexes", [])
    pollutants = raw.get("pollutants", [])
    health_recs = raw.get("healthRecommendations", {})

    aqi_local: int | None = None
    category_local = "MODERATE"
    dominant_pollutant = "pm25"
    aqi_universal: int | None = None

    for idx in indexes:
        code = str(idx.get("code", "")).lower()
        if code in ("ind_cpcb", "cpcb"):
            aqi_local = idx.get("aqi")
            category_local = str(idx.get("category", "MODERATE"))
            dominant_pollutant = str(idx.get("dominantPollutant", dominant_pollutant))
        elif code == "uaqi":
            aqi_universal = idx.get("aqi")

    pm25_ug = 0.0
    pm10_ug: float | None = None
    for p in pollutants:
        p_code = str(p.get("code", "")).lower()
        val = p.get("concentration", {}).get("value")
        if val is not None:
            if p_code == "pm25":
                pm25_ug = float(val)
            elif p_code == "pm10":
                pm10_ug = float(val)

    recs: dict[str, str] = (
        {k: v for k, v in health_recs.items() if isinstance(v, str)}
        if isinstance(health_recs, dict)
        else {}
    )
    time_local = date_time[11:16] if len(date_time) >= MIN_ISO_TIME_LEN else date_time

    return HourlyAirPoint(
        time_utc=date_time,
        time_local=time_local,
        pm25_ug_m3=pm25_ug,
        pm10_ug_m3=pm10_ug,
        aqi_local=aqi_local,
        aqi_universal=aqi_universal,
        category_local=category_local,
        dominant_pollutant=dominant_pollutant,
        health_recs=recs,
    )


def _load_nearest_fixture(
    lat: float,
    lng: float,
    hours: int,
    demo_clock_iso: str | None = None,
) -> HourlyAirSeries:
    """Load and time-shift geographically closest winter fixture."""
    d_ncr = _haversine_km(lat, lng, DELHI_NCR_COORDS[0], DELHI_NCR_COORDS[1])
    d_chd = _haversine_km(lat, lng, CHANDIGARH_COORDS[0], CHANDIGARH_COORDS[1])
    fixture_name = (
        "chandigarh_mohali_winter.json" if d_chd < d_ncr else "delhi_gurugram_winter.json"
    )
    fixture_path = DATA_ROOT / fixture_name

    with fixture_path.open(encoding="utf-8") as f:
        payload = json.load(f)

    raw_forecasts = payload.get("hourlyForecasts", [])
    now_dt = datetime.now(UTC)
    if demo_clock_iso:
        with contextlib.suppress(ValueError):
            now_dt = datetime.fromisoformat(demo_clock_iso.replace("Z", "+00:00"))

    points: list[HourlyAirPoint] = []
    max_h = min(hours, len(raw_forecasts))
    for i in range(max_h):
        pt = _normalise_raw_forecast_point(raw_forecasts[i])
        hour_val = (now_dt.hour + i) % 24
        points.append(
            HourlyAirPoint(
                time_utc=pt.time_utc,
                time_local=f"{hour_val:02d}:00",
                pm25_ug_m3=pt.pm25_ug_m3,
                pm10_ug_m3=pt.pm10_ug_m3,
                aqi_local=pt.aqi_local,
                aqi_universal=pt.aqi_universal,
                category_local=pt.category_local,
                dominant_pollutant=pt.dominant_pollutant,
                health_recs=pt.health_recs,
            )
        )

    return HourlyAirSeries(
        points=points,
        location_cell=f"{lat:.2f},{lng:.2f}",
        data_mode="fixture",
        fetched_at=now_dt.isoformat(),
    )


class AirQualityClient:
    """Client for Google Maps Platform Air Quality API with caching and fallback."""

    def __init__(
        self,
        settings: Settings,
        cache: CacheBackend,
        http_client: httpx.AsyncClient,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        """Initialize AirQualityClient with settings, cache, and HTTP client."""
        self._settings = settings
        self._cache = cache
        self._http = http_client
        self._breaker = breaker or CircuitBreaker()

    async def _save_cache(self, key: str, series: HourlyAirSeries) -> None:
        await self._cache.set(
            key,
            {
                "points": [asdict(p) for p in series.points],
                "location_cell": series.location_cell,
                "data_mode": series.data_mode,
                "fetched_at": series.fetched_at,
            },
            ttl_s=self._settings.aq_cache_ttl_s,
        )

    async def get_hourly_forecast(
        self,
        lat: float,
        lng: float,
        hours: int = 24,
        language_code: str = "en",
    ) -> HourlyAirSeries:
        """Retrieve hourly air quality forecast with caching, retries, and fallback."""
        r_lat, r_lng = round_coordinates(lat, lng)
        now_bucket = int(time.time() // 1800)
        cache_key = f"aq:forecast:{r_lat}:{r_lng}:{hours}:{language_code}:{now_bucket}"

        cached = await self._cache.get(cache_key)
        if isinstance(cached, dict):
            pts_raw = cached.get("points")
            points = (
                [HourlyAirPoint(**p) for p in pts_raw if isinstance(p, dict)]
                if isinstance(pts_raw, list)
                else []
            )
            data_mode: Literal["live", "fixture"] = (
                "live" if cached.get("data_mode") == "live" else "fixture"
            )
            return HourlyAirSeries(
                points=points,
                location_cell=str(cached.get("location_cell", f"{r_lat},{r_lng}")),
                data_mode=data_mode,
                fetched_at=str(cached.get("fetched_at", "")),
            )

        api_key = (
            self._settings.google_maps_api_key.get_secret_value()
            if self._settings.google_maps_api_key
            else None
        )

        if not api_key or not self._breaker.can_execute():
            series = _load_nearest_fixture(
                r_lat, r_lng, hours, demo_clock_iso=self._settings.demo_clock_iso
            )
            await self._save_cache(cache_key, series)
            return series

        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key}
        body = {
            "location": {"latitude": r_lat, "longitude": r_lng},
            "universalAqi": True,
            "languageCode": language_code,
            "extraComputations": [
                "LOCAL_AQI",
                "HEALTH_RECOMMENDATIONS",
                "POLLUTANT_CONCENTRATION",
                "DOMINANT_POLLUTANT_CONCENTRATION",
            ],
            "pageSize": min(96, max(1, hours)),
        }
        url = f"{AQ_API_BASE}/forecast:lookup"

        for attempt in (1, MAX_RETRY_ATTEMPTS):
            try:
                resp = await self._http.post(
                    url, json=body, headers=headers, timeout=self._settings.aq_timeout_s
                )
                if resp.status_code == HTTP_OK:
                    self._breaker.record_success()
                    raw_forecasts = resp.json().get("hourlyForecasts", [])
                    series = HourlyAirSeries(
                        points=[_normalise_raw_forecast_point(rf) for rf in raw_forecasts[:hours]],
                        location_cell=f"{r_lat:.2f},{r_lng:.2f}",
                        data_mode="live",
                        fetched_at=datetime.now(UTC).isoformat(),
                    )
                    await self._save_cache(cache_key, series)
                    return series

                if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRY_ATTEMPTS:
                    await asyncio.sleep(0.1 + random.uniform(0.05, 0.15))  # noqa: S311
                    continue
                self._breaker.record_failure()
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < MAX_RETRY_ATTEMPTS:
                    await asyncio.sleep(0.1 + random.uniform(0.05, 0.15))  # noqa: S311
                    continue
                self._breaker.record_failure()
                break

        series = _load_nearest_fixture(
            r_lat, r_lng, hours, demo_clock_iso=self._settings.demo_clock_iso
        )
        await self._save_cache(cache_key, series)
        return series

    async def get_current_conditions(
        self,
        lat: float,
        lng: float,
        language_code: str = "en",
    ) -> HourlyAirPoint:
        """Retrieve current air quality conditions (first hour of forecast)."""
        series = await self.get_hourly_forecast(lat, lng, hours=1, language_code=language_code)
        if series.points:
            return series.points[0]
        return HourlyAirPoint(
            time_utc=datetime.now(UTC).isoformat(),
            time_local="12:00",
            pm25_ug_m3=150.0,
            pm10_ug_m3=240.0,
            aqi_local=320,
            aqi_universal=35,
            category_local="VERY_POOR",
            dominant_pollutant="pm25",
            health_recs={},
        )
