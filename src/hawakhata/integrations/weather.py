"""Open-Meteo Weather & Atmospheric Dispersion API client with caching and fallback."""

from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

import httpx

from hawakhata.core.logging import get_logger
from hawakhata.integrations.air_quality import CircuitBreaker, round_coordinates

if TYPE_CHECKING:
    from hawakhata.config import Settings
    from hawakhata.core.cache import CacheBackend

logger = get_logger(__name__)
WEATHER_API_BASE = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True, slots=True)
class HourlyWeatherPoint:
    """Normalised single-hour atmospheric observation."""

    time_local: str
    temperature_c: float
    relative_humidity_pct: float
    wind_speed_kmh: float
    precipitation_mm: float
    boundary_layer_height_m: float


@dataclass(frozen=True, slots=True)
class HourlyWeatherSeries:
    """Normalised multi-hour weather series."""

    points: list[HourlyWeatherPoint]
    location_cell: str
    data_mode: Literal["live", "fixture"]
    fetched_at: str


def generate_synthetic_winter_weather(
    lat: float, lng: float, hours: int = 96
) -> HourlyWeatherSeries:
    """Generate deterministic synthetic winter weather series for northern Indian plains."""
    points: list[HourlyWeatherPoint] = []
    for h in range(hours):
        tod, day = h % 24, h // 24
        temp = round(17.0 + 7.0 * math.sin((tod - 8) * math.pi / 12) + (day * 0.3), 1)
        rh = round(max(20.0, min(95.0, 60.0 - 22.0 * math.sin((tod - 8) * math.pi / 12) - day)), 1)
        wind_base = 4.0 if (tod < 10 or tod > 19) else 11.5
        wind = round(
            max(
                1.0,
                wind_base
                + 3.0 * math.sin((tod - 10) * math.pi / 6)
                + (4.5 if (day == 2 and 12 <= tod <= 16) else 0.0),
            ),
            1,
        )
        blh = (
            round(850.0 + 350.0 * math.sin((tod - 11) * math.pi / 5), 1)
            if 11 <= tod <= 16
            else round(210.0 + 35.0 * ((tod + day) % 4), 1)
        )
        points.append(
            HourlyWeatherPoint(f"2026-11-{(19 + day):02d}T{tod:02d}:00", temp, rh, wind, 0.0, blh)
        )
    return HourlyWeatherSeries(
        points, f"{round(lat, 2)},{round(lng, 2)}", "fixture", "2026-11-19T00:00:00Z"
    )


class WeatherClient:
    """Open-Meteo weather forecast client with privacy rounding, caching, and circuit breaker."""

    def __init__(
        self,
        settings: Settings,
        cache: CacheBackend,
        http_client: httpx.AsyncClient,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._settings, self._cache, self._http = settings, cache, http_client
        self._breaker = breaker or CircuitBreaker(failure_threshold=3, recovery_time_s=60.0)

    async def _save_cache(self, key: str, series: HourlyWeatherSeries) -> None:
        if self._cache is not None:
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

    async def get_hourly_weather(
        self, lat: float, lng: float, hours: int = 96
    ) -> HourlyWeatherSeries:
        """Fetch 96-hour hourly weather with caching, circuit breaker, and synthetic fallback."""
        r_lat, r_lng = round_coordinates(lat, lng)
        cache_key = f"weather:forecast:{r_lat}:{r_lng}:{hours}:{int(time.time() // 1800)}"

        cached = await self._cache.get(cache_key) if self._cache is not None else None
        if isinstance(cached, dict):
            raw_pts = cached.get("points")
            if isinstance(raw_pts, list):
                pts = [HourlyWeatherPoint(**p) for p in raw_pts if isinstance(p, dict)]
                mode: Literal["live", "fixture"] = (
                    "live" if cached.get("data_mode") == "live" else "fixture"
                )
                return HourlyWeatherSeries(
                    pts,
                    str(cached.get("location_cell", f"{r_lat},{r_lng}")),
                    mode,
                    str(cached.get("fetched_at", "")),
                )

        if not self._breaker.can_execute() or self._settings.app_env == "test":
            synth = generate_synthetic_winter_weather(r_lat, r_lng, hours=hours)
            await self._save_cache(cache_key, synth)
            return synth

        query_params: dict[str, str | int | float] = {
            "latitude": r_lat,
            "longitude": r_lng,
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,boundary_layer_height",
            "forecast_days": min(4, max(1, math.ceil(hours / 24))),
            "timezone": "auto",
        }

        for attempt in range(2):
            try:
                resp = await self._http.get(
                    WEATHER_API_BASE, params=query_params, timeout=self._settings.aq_timeout_s
                )
                if resp.status_code == 200:
                    d = resp.json().get("hourly", {})
                    times, temps, rhs = (
                        d.get("time", []),
                        d.get("temperature_2m", []),
                        d.get("relative_humidity_2m", []),
                    )
                    winds, precips, blhs = (
                        d.get("wind_speed_10m", []),
                        d.get("precipitation", []),
                        d.get("boundary_layer_height", []),
                    )
                    pts = [
                        HourlyWeatherPoint(
                            str(times[i]),
                            float(temps[i]) if i < len(temps) else 20.0,
                            float(rhs[i]) if i < len(rhs) else 50.0,
                            float(winds[i]) if i < len(winds) else 8.0,
                            float(precips[i]) if i < len(precips) else 0.0,
                            float(blhs[i]) if i < len(blhs) else 500.0,
                        )
                        for i in range(min(hours, len(times)))
                    ]
                    self._breaker.record_success()
                    series = HourlyWeatherSeries(
                        pts,
                        f"{r_lat},{r_lng}",
                        "live",
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    )
                    await self._save_cache(cache_key, series)
                    return series
                self._breaker.record_failure()
            except (TimeoutError, httpx.RequestError):
                self._breaker.record_failure()
                if attempt < 1:
                    await asyncio.sleep(0.05 + random.uniform(0.01, 0.05))  # noqa: S311

        fallback = generate_synthetic_winter_weather(r_lat, r_lng, hours=hours)
        await self._save_cache(cache_key, fallback)
        return fallback
