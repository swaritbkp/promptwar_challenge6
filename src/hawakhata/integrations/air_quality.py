"""Live air quality client: Open-Meteo (primary) -> Google AQ (secondary) -> offline fixture.

Open-Meteo Air Quality is keyless and covers every coordinate in India with real hourly
PM2.5 + PM10, so it is the primary live provider. Google Maps Air Quality is used only if
Open-Meteo fails and a key is configured. The offline fixture is used in ``app_env=test``
or when both live providers fail. Live readings are never rescaled.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import random
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

from hawakhata.core.logging import get_logger
from hawakhata.core.metrics import UPSTREAM_ERRORS
from hawakhata.engine.aqi import pm25_to_naqi_category, pm25_to_sub_index
from hawakhata.engine.constants import get_constant
from hawakhata.engine.planner import align_to_clock

if TYPE_CHECKING:
    from hawakhata.config import Settings
    from hawakhata.core.cache import CacheBackend

logger = get_logger(__name__)
DATA_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "fixtures"
AQ_API_BASE = "https://airquality.googleapis.com/v1"
OPEN_METEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
Provider = Literal["open_meteo_live", "google_aq_live", "fixture"]
PROVIDER_LABELS: dict[str, str] = {
    "open_meteo_live": "Open-Meteo Live AQ",
    "google_aq_live": "Google Air Quality API",
    "fixture": "Offline Synthetic Fixture",
}
DELHI_NCR_COORDS = (28.4595, 77.0266)
CHANDIGARH_COORDS = (30.7333, 76.7794)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


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
    provider: str = "fixture"
    data_source: str = PROVIDER_LABELS["fixture"]

    @property
    def start_hour(self) -> int:
        """Local (IST) clock hour of the first reading, used to clock-align series."""
        tl = self.points[0].time_local if self.points else ""
        return int(tl[:2]) if len(tl) >= 2 and tl[:2].isdigit() else 0

    @property
    def fetched_at_ist(self) -> str:
        """Freshness stamp such as ``"18:30 IST"`` (empty if unknown)."""
        with contextlib.suppress(ValueError):
            dt = datetime.fromisoformat(self.fetched_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return f"{dt.astimezone(IST):%H:%M} IST"
        return ""


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
    time_local = dt[11:16] if len(dt) >= 16 else dt
    if dt:
        with contextlib.suppress(Exception):
            p_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            if p_dt.tzinfo is None:
                p_dt = p_dt.replace(tzinfo=UTC)
            time_local = f"{p_dt.astimezone(IST).hour:02d}:00"
    return HourlyAirPoint(dt, time_local, pm25, pm10, aqi_l, aqi_u, cat_l, dom, recs)


def _point_from_pm(
    dt_ist: datetime, pm25: float, pm10: float | None, aqi_u: int | None = None
) -> HourlyAirPoint:
    pm25 = round(max(0.0, pm25), 1)
    return HourlyAirPoint(
        dt_ist.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        f"{dt_ist.hour:02d}:00",
        pm25,
        None if pm10 is None else round(max(0.0, pm10), 1),
        pm25_to_sub_index(pm25),
        aqi_u,
        pm25_to_naqi_category(pm25).display_name,
        "pm25",
        {},
    )


def parse_open_meteo_hourly(
    payload: dict[str, Any], hours: int, now_ist: datetime
) -> list[HourlyAirPoint]:
    """Normalise an Open-Meteo ``hourly`` block (IST timestamps) starting at the current hour.

    Values pass through unmodified; a missing hour carries the previous valid reading.
    Raises ValueError if the payload holds no usable PM2.5.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    pm25s = hourly.get("pm2_5") or []
    pm10s = hourly.get("pm10") or []
    current = now_ist.strftime("%Y-%m-%dT%H:00")
    start = next((i for i, t in enumerate(times) if str(t) >= current), len(times))
    pts: list[HourlyAirPoint] = []
    last_pm25: float | None = None
    for i in range(start, min(len(times), start + hours)):
        raw25 = pm25s[i] if i < len(pm25s) else None
        raw10 = pm10s[i] if i < len(pm10s) else None
        if raw25 is not None:
            last_pm25 = float(raw25)
        if last_pm25 is None:
            continue
        dt_ist = datetime.fromisoformat(str(times[i])).replace(tzinfo=IST)
        pts.append(_point_from_pm(dt_ist, last_pm25, None if raw10 is None else float(raw10)))
    if not pts:
        raise ValueError("Open-Meteo payload contained no PM2.5 readings")
    return pts


def resolve_city_scale(lat: float, lng: float) -> float:
    """Fixture-mode PM2.5 scale for the nearest metro (data/constants.v1.json)."""
    cfg = get_constant("city_pm25_fixture_scale").value
    min_dist, best_scale = float("inf"), 1.0
    for c_lat, c_lng, s, _name in cfg["anchors"]:
        d = _haversine_km(lat, lng, float(c_lat), float(c_lng))
        if d < min_dist:
            min_dist, best_scale = d, float(s)
    if min_dist <= float(cfg["max_match_km"]):
        return best_scale
    south = lat < float(cfg["fallback_split_lat"])
    return float(cfg["fallback_south"] if south else cfg["fallback_north"])


def _load_nearest_fixture(
    lat: float, lng: float, hours: int, demo_clock_iso: str | None = None
) -> HourlyAirSeries:
    d_n = _haversine_km(lat, lng, DELHI_NCR_COORDS[0], DELHI_NCR_COORDS[1])
    d_c = _haversine_km(lat, lng, CHANDIGARH_COORDS[0], CHANDIGARH_COORDS[1])
    p = DATA_ROOT / ("chandigarh_mohali_winter.json" if d_c < d_n else "delhi_gurugram_winter.json")
    raw = json.loads(p.read_text("utf-8")).get("hourlyForecasts", [])
    now_dt = datetime.now(IST)
    if demo_clock_iso:
        with contextlib.suppress(ValueError):
            p_dt = datetime.fromisoformat(demo_clock_iso.replace("Z", "+00:00"))
            now_dt = p_dt

    scale = resolve_city_scale(lat, lng)
    # Day-to-day synoptic modifier: Today (1.0), Tomorrow (+10% inversion trap), Day 3 (-18% mixing lift), Day 4 (recovery)
    synoptic_mods = [1.00, 1.10, 0.82, 0.92]

    pts = []
    num_raw = len(raw) if raw else 1
    for i in range(hours):
        tod = (now_dt.hour + i) % num_raw
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
                pt_dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    """Live AQ client: Open-Meteo primary, Google AQ secondary, offline fixture last."""

    def __init__(
        self,
        settings: Settings,
        cache: CacheBackend,
        http_client: httpx.AsyncClient,
        breaker: CircuitBreaker | None = None,
        open_meteo_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings, self._cache, self._http = settings, cache, http_client
        self._breaker = breaker or CircuitBreaker()
        self._om_breaker = open_meteo_breaker or CircuitBreaker()

    def breaker_states(self) -> dict[str, str]:
        """Current provider circuit-breaker states (read-only operational telemetry)."""
        return {"open_meteo": self._om_breaker.state.value, "google_aq": self._breaker.state.value}

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
                "provider": series.provider,
            },
            ttl_s=self._settings.aq_cache_ttl_s,
        )

    @staticmethod
    def _from_cache(cached: dict[str, Any], cell: str) -> HourlyAirSeries:
        pts_raw = cached.get("points")
        points = (
            [HourlyAirPoint(**p) for p in pts_raw if isinstance(p, dict)]
            if isinstance(pts_raw, list)
            else []
        )
        provider = str(cached.get("provider", "fixture"))
        if provider not in PROVIDER_LABELS:
            provider = "fixture"
        return HourlyAirSeries(
            points,
            str(cached.get("location_cell", cell)),
            "fixture" if provider == "fixture" else "live",
            str(cached.get("fetched_at", "")),
            provider,
            PROVIDER_LABELS[provider],
        )

    async def _fetch_open_meteo(self, lat: float, lng: float, hours: int) -> HourlyAirSeries | None:
        """Query keyless Open-Meteo AQ; forecast_days=5 keeps 96 future hours after trimming."""
        if not self._om_breaker.can_execute():
            return None
        params: dict[str, str | int | float] = {
            "latitude": lat,
            "longitude": lng,
            "hourly": "pm2_5,pm10",
            "forecast_days": 5,
            "timezone": "Asia/Kolkata",
        }
        for attempt in (1, 2):
            try:
                resp = await self._http.get(
                    OPEN_METEO_AQ_URL, params=params, timeout=self._settings.aq_timeout_s
                )
                if resp.status_code == 200:
                    pts = parse_open_meteo_hourly(resp.json(), hours, datetime.now(IST))
                    self._om_breaker.record_success()
                    return HourlyAirSeries(
                        pts,
                        f"{lat:.2f},{lng:.2f}",
                        "live",
                        datetime.now(UTC).isoformat(),
                        "open_meteo_live",
                        PROVIDER_LABELS["open_meteo_live"],
                    )
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                UPSTREAM_ERRORS.inc(provider="open_meteo")
                logger.info("Open-Meteo AQ attempt %d failed: %s", attempt, type(exc).__name__)
        self._om_breaker.record_failure()
        return None

    async def _fetch_google(
        self, lat: float, lng: float, hours: int, language_code: str
    ) -> HourlyAirSeries | None:
        api_key = (
            self._settings.google_maps_api_key.get_secret_value()
            if self._settings.google_maps_api_key
            else None
        )
        if not api_key or not self._breaker.can_execute():
            return None
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": api_key}
        body = {
            "location": {"latitude": lat, "longitude": lng},
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
        for attempt in (1, 2):
            try:
                resp = await self._http.post(
                    f"{AQ_API_BASE}/forecast:lookup",
                    json=body,
                    headers=headers,
                    timeout=self._settings.aq_timeout_s,
                )
                raw = resp.json().get("hourlyForecasts", []) if resp.status_code == 200 else []
                if raw:
                    self._breaker.record_success()
                    return HourlyAirSeries(
                        [_normalise_raw_forecast_point(rf) for rf in raw[:hours]],
                        f"{lat:.2f},{lng:.2f}",
                        "live",
                        datetime.now(UTC).isoformat(),
                        "google_aq_live",
                        PROVIDER_LABELS["google_aq_live"],
                    )
            except (httpx.HTTPError, ValueError) as exc:
                UPSTREAM_ERRORS.inc(provider="google_aq")
                logger.info("Google AQ attempt %d failed: %s", attempt, type(exc).__name__)
            if attempt < 2:
                await asyncio.sleep(0.1 + random.uniform(0.05, 0.15))  # noqa: S311
        self._breaker.record_failure()
        return None

    async def get_hourly_forecast(
        self, lat: float, lng: float, hours: int = 24, language_code: str = "en"
    ) -> HourlyAirSeries:
        """Hourly PM2.5/PM10 starting at the current IST hour, via the provider chain.

        Chain (outside ``app_env == "test"``): Open-Meteo live -> Google AQ live (only if a
        key is set) -> offline fixture. Tests always use the deterministic fixture.
        """
        r_lat, r_lng = round_coordinates(lat, lng)
        # One upstream call per ~1 km cell per 30 min: always fetch 96 h, slice per caller.
        span = max(96, hours)
        cache_key = f"aq:forecast:{r_lat}:{r_lng}:{span}:{language_code}:{int(time.time() // 1800)}"
        cached = await self._cache.get(cache_key) if self._cache is not None else None
        if isinstance(cached, dict):
            return _slice(self._from_cache(cached, f"{r_lat},{r_lng}"), hours)

        series: HourlyAirSeries | None = None
        if self._settings.app_env != "test":
            series = await self._fetch_open_meteo(r_lat, r_lng, span)
            if series is None:
                series = await self._fetch_google(r_lat, r_lng, span, language_code)
        if series is None:
            series = _load_nearest_fixture(
                r_lat, r_lng, span, demo_clock_iso=self._settings.demo_clock_iso
            )
        await self._save_cache(cache_key, series)
        return _slice(series, hours)

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


def _slice(series: HourlyAirSeries, hours: int) -> HourlyAirSeries:
    if len(series.points) <= hours:
        return series
    return replace(series, points=series.points[:hours])


def clock_aligned_pm25(series: HourlyAirSeries, hours: int = 24) -> list[float]:
    """PM2.5 values re-indexed so position h is clock hour h (see ``align_to_clock``)."""
    return align_to_clock([p.pm25_ug_m3 for p in series.points], series.start_hour)[:hours]
