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
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

from hawakhata.core.logging import get_logger
from hawakhata.engine.aqi import pm25_to_naqi_category, pm25_to_sub_index

if TYPE_CHECKING:
    from hawakhata.config import Settings
    from hawakhata.core.cache import CacheBackend

logger = get_logger(__name__)
DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "fixtures"
AQ_API_BASE = "https://airquality.googleapis.com/v1"
DELHI_NCR_COORDS = (28.4595, 77.0266)
CHANDIGARH_COORDS = (30.7333, 76.7794)


def round_coordinates(lat: float, lng: float) -> tuple[float, float]:
    """Round coordinates to 2 decimal places (~1.1 km precision)."""
    return round(lat, 2), round(lng, 2)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat, d_lon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2.0) ** 2
    )
    return 6371.0 * (2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))


class CircuitState(StrEnum):
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
        self._threshold, self._recovery_s = failure_threshold, recovery_time_s
        self._clock, self._state, self._failures, self._last_failure = (
            clock or time.monotonic,
            CircuitState.CLOSED,
            0,
            0.0,
        )

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and (self._clock() - self._last_failure) >= self._recovery_s
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def can_execute(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        self._failures, self._state = 0, CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure = self._clock()
        if self._failures >= self._threshold:
            self._state = CircuitState.OPEN
            logger.warning("AQ circuit breaker OPENED after %d failures", self._failures)


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
    dt = str(raw.get("dateTime", ""))
    aqi_l, cat_l, dom, aqi_u = None, "MODERATE", "pm25", None
    for idx in raw.get("indexes", []):
        code = str(idx.get("code", "")).lower()
        if code in ("ind_cpcb", "cpcb"):
            aqi_l, cat_l, dom = (
                idx.get("aqi"),
                str(idx.get("category", "MODERATE")),
                str(idx.get("dominantPollutant", dom)),
            )
        elif code == "uaqi":
            aqi_u = idx.get("aqi")

    pm25, pm10 = 0.0, None
    for p in raw.get("pollutants", []):
        c, val = str(p.get("code", "")).lower(), p.get("concentration", {}).get("value")
        if val is not None:
            if c == "pm25":
                pm25 = float(val)
            elif c == "pm10":
                pm10 = float(val)

    recs = {k: v for k, v in raw.get("healthRecommendations", {}).items() if isinstance(v, str)}
    return HourlyAirPoint(
        dt, dt[11:16] if len(dt) >= 16 else dt, pm25, pm10, aqi_l, aqi_u, cat_l, dom, recs
    )


CITY_CALIBRATED_SCALES: list[tuple[float, float, float]] = [
    (28.4595, 77.0266, 1.00),  # Northern Plains primary baseline (~320-380 µg/m³, AQI 420-434)
    (30.7333, 76.7794, 0.75),  # Northern Foothills baseline (~180-240 µg/m³, AQI 350)
    (19.0760, 72.8777, 0.20),  # Mumbai (~64 µg/m³, AQI 113 Moderate)
    (12.9716, 77.5946, 0.14),  # Bengaluru (~45 µg/m³, Satisfactory)
    (22.5726, 88.3639, 0.50),  # Kolkata (~160 µg/m³, Very Poor)
    (13.0827, 80.2707, 0.13),  # Chennai (~42 µg/m³, Satisfactory)
    (17.3850, 78.4867, 0.20),  # Hyderabad (~64 µg/m³, Moderate)
    (18.5204, 73.8567, 0.20),  # Pune (~64 µg/m³, Moderate)
    (26.9124, 75.7873, 0.45),  # Jaipur (~144 µg/m³, Very Poor)
    (26.8467, 80.9462, 0.88),  # Lucknow (~280 µg/m³, Severe)
    (25.5941, 85.1376, 0.94),  # Patna (~300 µg/m³, Severe)
    (23.0225, 72.5714, 0.40),  # Ahmedabad (~128 µg/m³, Very Poor)
]


def resolve_city_scale(lat: float, lng: float) -> float:
    """Resolve calibrated scaling factor based on nearest Indian metro coordinates."""
    min_dist, best_scale = float("inf"), 1.0
    for c_lat, c_lng, s in CITY_CALIBRATED_SCALES:
        d = _haversine_km(lat, lng, c_lat, c_lng)
        if d < min_dist:
            min_dist, best_scale = d, s
    if min_dist <= 200.0:
        return best_scale
    return 0.20 if lat < 21.0 else 0.70


def _load_nearest_fixture(
    lat: float, lng: float, hours: int, demo_clock_iso: str | None = None
) -> HourlyAirSeries:
    d_n = _haversine_km(lat, lng, DELHI_NCR_COORDS[0], DELHI_NCR_COORDS[1])
    d_c = _haversine_km(lat, lng, CHANDIGARH_COORDS[0], CHANDIGARH_COORDS[1])
    p = DATA_ROOT / ("chandigarh_mohali_winter.json" if d_c < d_n else "delhi_gurugram_winter.json")
    raw = json.loads(p.read_text("utf-8")).get("hourlyForecasts", [])
    now_dt = datetime.now(UTC)
    if demo_clock_iso:
        with contextlib.suppress(ValueError):
            now_dt = datetime.fromisoformat(demo_clock_iso.replace("Z", "+00:00"))

    scale = resolve_city_scale(lat, lng)
    # Day-to-day synoptic modifier: Today (1.0), Tomorrow (+10% inversion trap), Day 3 (-18% mixing lift), Day 4 (recovery)
    synoptic_mods = [1.00, 1.10, 0.82, 0.92]

    pts = []
    num_raw = len(raw) if raw else 1
    for i in range(hours):
        tod = i % num_raw
        day_idx = min(3, i // 24)
        day_mod = synoptic_mods[day_idx]
        norm = _normalise_raw_forecast_point(raw[tod])
        p_pm25 = round(norm.pm25_ug_m3 * scale * day_mod, 1)
        p_pm10 = (
            round(norm.pm10_ug_m3 * scale * day_mod, 1) if norm.pm10_ug_m3 is not None else None
        )
        sub_idx = pm25_to_sub_index(p_pm25)
        cat = pm25_to_naqi_category(p_pm25)
        pt_dt = now_dt + timedelta(hours=i)
        pts.append(
            HourlyAirPoint(
                pt_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"{(now_dt.hour + i) % 24:02d}:00",
                p_pm25,
                p_pm10,
                sub_idx,
                norm.aqi_universal,
                cat.display_name,
                norm.dominant_pollutant,
                norm.health_recs,
            )
        )
    return HourlyAirSeries(pts, f"{lat:.2f},{lng:.2f}", "fixture", now_dt.isoformat())


class AirQualityClient:
    """Client for Google Maps Platform Air Quality API with caching and fallback."""

    def __init__(
        self,
        settings: Settings,
        cache: CacheBackend,
        http_client: httpx.AsyncClient,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings, self._cache, self._http = settings, cache, http_client
        self._breaker = breaker or CircuitBreaker()

    async def _save_cache(self, key: str, series: HourlyAirSeries) -> None:
        if self._cache is None:
            return
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
        self, lat: float, lng: float, hours: int = 24, language_code: str = "en"
    ) -> HourlyAirSeries:
        """Retrieve hourly air quality forecast with caching, retries, and fallback."""
        r_lat, r_lng = round_coordinates(lat, lng)
        now_bucket = int(time.time() // 1800)
        cache_key = f"aq:forecast:{r_lat}:{r_lng}:{hours}:{language_code}:{now_bucket}"

        cached = await self._cache.get(cache_key) if self._cache is not None else None
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
                points,
                str(cached.get("location_cell", f"{r_lat},{r_lng}")),
                data_mode,
                str(cached.get("fetched_at", "")),
            )

        api_key = (
            self._settings.google_maps_api_key.get_secret_value()
            if self._settings.google_maps_api_key
            else None
        )
        if not api_key or not self._breaker.can_execute():
            s = _load_nearest_fixture(
                r_lat, r_lng, hours, demo_clock_iso=self._settings.demo_clock_iso
            )
            await self._save_cache(cache_key, s)
            return s

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

        for attempt in (1, 2):
            try:
                resp = await self._http.post(
                    url, json=body, headers=headers, timeout=self._settings.aq_timeout_s
                )
                if resp.status_code == 200:
                    self._breaker.record_success()
                    raw = resp.json().get("hourlyForecasts", [])
                    s = HourlyAirSeries(
                        [_normalise_raw_forecast_point(rf) for rf in raw[:hours]],
                        f"{r_lat:.2f},{r_lng:.2f}",
                        "live",
                        datetime.now(UTC).isoformat(),
                    )
                    await self._save_cache(cache_key, s)
                    return s
            except (httpx.TimeoutException, httpx.NetworkError):
                pass
            if attempt < 2:
                await asyncio.sleep(0.1 + random.uniform(0.05, 0.15))  # noqa: S311
                continue
            self._breaker.record_failure()
            break

        s = _load_nearest_fixture(r_lat, r_lng, hours, demo_clock_iso=self._settings.demo_clock_iso)
        await self._save_cache(cache_key, s)
        return s

    async def get_current_conditions(
        self, lat: float, lng: float, language_code: str = "en"
    ) -> HourlyAirPoint:
        """Retrieve current air quality conditions (first hour of forecast)."""
        series = await self.get_hourly_forecast(lat, lng, hours=1, language_code=language_code)
        if series.points:
            return series.points[0]
        return HourlyAirPoint(
            datetime.now(UTC).isoformat(), "12:00", 150.0, 240.0, 320, 35, "VERY_POOR", "pm25", {}
        )
