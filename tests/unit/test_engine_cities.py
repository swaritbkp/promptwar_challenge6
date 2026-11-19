"""Tests for hawakhata.engine.cities — city catalog and nearest-city matching."""

from __future__ import annotations

import pytest

from hawakhata.engine.cities import (
    CityInfo,
    find_nearest_city,
    get_supported_cities,
    haversine_distance_km,
)

# ---------------------------------------------------------------------------
# City catalog
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {"id", "name", "lat", "lng", "state"}
KNOWN_CITY_NAMES = {
    "Delhi NCR / Gurugram",
    "Chandigarh / Mohali",
    "Mumbai",
    "Bengaluru",
    "Kolkata",
    "Chennai",
    "Hyderabad",
    "Pune",
    "Jaipur",
    "Lucknow",
    "Patna",
    "Ahmedabad",
}


def test_get_supported_cities_returns_list() -> None:
    cities = get_supported_cities()
    assert isinstance(cities, list)
    assert len(cities) >= 2


def test_all_known_cities_present() -> None:
    cities = get_supported_cities()
    names = {c.name for c in cities}
    assert KNOWN_CITY_NAMES.issubset(names), f"Missing: {KNOWN_CITY_NAMES - names}"


def test_city_required_fields() -> None:
    for city in get_supported_cities():
        assert isinstance(city, CityInfo)
        assert city.id, "id must be non-empty"
        assert city.name, "name must be non-empty"
        assert -90.0 <= city.lat <= 90.0, f"Invalid lat for {city.name}"
        assert -180.0 <= city.lng <= 180.0, f"Invalid lng for {city.name}"
        assert isinstance(city.state, str)


def test_all_cities_in_india_bounds() -> None:
    """All cities should be within rough India bounding box."""
    for city in get_supported_cities():
        assert 6.0 <= city.lat <= 38.0, f"{city.name} lat={city.lat} out of India"
        assert 68.0 <= city.lng <= 98.0, f"{city.name} lng={city.lng} out of India"


def test_city_ids_are_unique() -> None:
    cities = get_supported_cities()
    ids = [c.id for c in cities]
    assert len(ids) == len(set(ids)), "Duplicate city IDs found"


def test_city_names_are_unique() -> None:
    cities = get_supported_cities()
    names = [c.name for c in cities]
    assert len(names) == len(set(names)), "Duplicate city names found"


def test_get_supported_cities_is_cached() -> None:
    """Calling twice returns the same list object (lru_cache)."""
    a = get_supported_cities()
    b = get_supported_cities()
    assert a is b


def test_get_supported_cities_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fallback when cities file is missing."""
    import hawakhata.engine.cities as cities_mod

    monkeypatch.setattr(cities_mod, "CITIES_PATH", cities_mod.ROOT / "nonexistent.json")
    get_supported_cities.cache_clear()
    try:
        res = get_supported_cities()
        assert len(res) == 2
        assert res[0].id == "c1"
    finally:
        get_supported_cities.cache_clear()


def test_delhi_ncr_coordinates() -> None:
    cities = {c.name: c for c in get_supported_cities()}
    delhi = cities["Delhi NCR / Gurugram"]
    assert pytest.approx(delhi.lat, abs=0.5) == 28.46
    assert pytest.approx(delhi.lng, abs=0.5) == 77.03


def test_chandigarh_coordinates() -> None:
    cities = {c.name: c for c in get_supported_cities()}
    chd = cities["Chandigarh / Mohali"]
    assert pytest.approx(chd.lat, abs=0.5) == 30.73
    assert pytest.approx(chd.lng, abs=0.5) == 76.78


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------


def test_haversine_same_point_is_zero() -> None:
    assert haversine_distance_km(28.46, 77.03, 28.46, 77.03) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance_delhi_mumbai() -> None:
    """Approximate straight-line distance Delhi ↔ Mumbai ~1150 km."""
    d = haversine_distance_km(28.46, 77.03, 19.08, 72.88)
    assert 1100.0 <= d <= 1250.0, f"Delhi-Mumbai distance {d:.1f} km out of expected range"


def test_haversine_symmetry() -> None:
    d1 = haversine_distance_km(28.46, 77.03, 12.97, 77.59)
    d2 = haversine_distance_km(12.97, 77.59, 28.46, 77.03)
    assert d1 == pytest.approx(d2, rel=1e-9)


def test_haversine_non_negative() -> None:
    for lat1, lng1, lat2, lng2 in [
        (0.0, 0.0, 90.0, 0.0),
        (28.4, 77.0, 30.7, 76.7),
        (-10.0, 50.0, 10.0, 60.0),
    ]:
        assert haversine_distance_km(lat1, lng1, lat2, lng2) >= 0.0


def test_haversine_equator_degree_approx_111km() -> None:
    """One degree of longitude at equator ≈ 111.3 km."""
    d = haversine_distance_km(0.0, 0.0, 0.0, 1.0)
    assert 110.0 <= d <= 113.0


# ---------------------------------------------------------------------------
# find_nearest_city
# ---------------------------------------------------------------------------


def test_find_nearest_city_exact_coords_delhi() -> None:
    cities = {c.name: c for c in get_supported_cities()}
    delhi = cities["Delhi NCR / Gurugram"]
    city, dist = find_nearest_city(delhi.lat, delhi.lng)
    assert city.name == "Delhi NCR / Gurugram"
    assert dist == pytest.approx(0.0, abs=0.01)


def test_find_nearest_city_exact_coords_chandigarh() -> None:
    cities = {c.name: c for c in get_supported_cities()}
    chd = cities["Chandigarh / Mohali"]
    city, dist = find_nearest_city(chd.lat, chd.lng)
    assert city.name == "Chandigarh / Mohali"
    assert dist == pytest.approx(0.0, abs=0.01)


def test_find_nearest_city_slightly_off_delhi() -> None:
    """Coords 5 km from Delhi should still resolve to Delhi NCR."""
    city, dist = find_nearest_city(28.5, 77.1)
    assert city.name == "Delhi NCR / Gurugram"
    assert 0 < dist < 20.0


def test_find_nearest_city_returns_tuple() -> None:
    result = find_nearest_city(28.46, 77.03)
    assert isinstance(result, tuple) and len(result) == 2
    assert isinstance(result[0], CityInfo)
    assert isinstance(result[1], float)


def test_find_nearest_city_distance_non_negative() -> None:
    for lat, lng in [(28.46, 77.03), (19.08, 72.88), (22.57, 88.36)]:
        _, dist = find_nearest_city(lat, lng)
        assert dist >= 0.0


def test_find_nearest_city_out_of_india() -> None:
    """Out-of-India coords should still return the closest city without crashing."""
    city, dist = find_nearest_city(0.0, 0.0)  # middle of Gulf of Guinea
    assert isinstance(city, CityInfo)
    assert dist > 1000.0  # far from any Indian city


def test_find_nearest_city_north_pole() -> None:
    city, dist = find_nearest_city(90.0, 0.0)
    assert isinstance(city, CityInfo)
    assert dist > 5000.0


def test_find_nearest_city_mumbai() -> None:
    cities = {c.name: c for c in get_supported_cities()}
    mumbai = cities["Mumbai"]
    city, dist = find_nearest_city(mumbai.lat, mumbai.lng)
    assert city.name == "Mumbai"
    assert dist == pytest.approx(0.0, abs=0.01)
