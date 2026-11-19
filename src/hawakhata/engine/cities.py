"""Supported Indian cities and nearest-city geographical matching."""

from __future__ import annotations

import functools
import json
import math
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
CITIES_PATH = ROOT / "data" / "cities.v1.json"


@dataclass(frozen=True, slots=True)
class CityInfo:
    """Geographical definition of a supported Indian city/metro."""

    id: str
    name: str
    lat: float
    lng: float
    state: str


@functools.lru_cache(maxsize=1)
def get_supported_cities() -> list[CityInfo]:
    """Return immutable list of supported Indian cities and metros."""
    if not CITIES_PATH.exists():
        return [
            CityInfo("c1", "Metro 1", 28.5, 77.0, "Region 1"),
            CityInfo("c2", "Metro 2", 30.7, 76.7, "Region 2"),
        ]
    data = json.loads(CITIES_PATH.read_text("utf-8"))
    return [
        CityInfo(
            id=str(c["id"]),
            name=str(c["name"]),
            lat=float(c["lat"]),
            lng=float(c["lng"]),
            state=str(c.get("state", "")),
        )
        for c in data
    ]


def haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance between two GPS coordinates in kilometers."""
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_km * c


def find_nearest_city(lat: float, lng: float) -> tuple[CityInfo, float]:
    """Find the closest supported city to the given coordinates."""
    cities = get_supported_cities()
    best_city, min_dist = cities[0], float("inf")
    for city in cities:
        dist = haversine_distance_km(lat, lng, city.lat, city.lng)
        if dist < min_dist:
            min_dist, best_city = dist, city
    return best_city, min_dist
