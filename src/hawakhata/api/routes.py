"""FastAPI router mounting all HawaKhata REST computing and data endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request

from hawakhata.api.dependencies import get_aq_client, make_meta
from hawakhata.api.schemas import (
    Envelope,
    ForecastRequest,
    IndoorSimulateRequest,
    PassbookRequest,
    PlanRequest,
    SwapsImpactRequest,
)
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.services.indoor_service import simulate_indoor_environment
from hawakhata.services.passbook_service import compute_family_passbook
from hawakhata.services.planner_service import compute_optimized_plan
from hawakhata.services.swap_service import compute_swap_impact, list_available_swaps

api_router = APIRouter(prefix="/api/v1")
AqClientDep = Annotated[AirQualityClient, Depends(get_aq_client)]


@api_router.post("/air/forecast", response_model=Envelope[dict[str, Any]], tags=["air"])
async def get_forecast(
    req: ForecastRequest,
    request: Request,
    aq_client: AqClientDep,
) -> Envelope[dict[str, Any]]:
    """Retrieve 24-96h normalised hourly PM2.5 and AQI series for a location."""
    series = await aq_client.get_hourly_forecast(
        lat=req.lat, lng=req.lng, hours=req.hours, language_code=req.language_code
    )
    meta = make_meta(request, data_mode=series.data_mode)
    return Envelope(data=asdict(series), meta=meta)


@api_router.post("/passbook", response_model=Envelope[dict[str, Any]], tags=["passbook"])
async def post_passbook(
    req: PassbookRequest,
    request: Request,
    aq_client: AqClientDep,
) -> Envelope[dict[str, Any]]:
    """Compute per-member inhaled dose, daily air budget, and balance."""
    loc = req.profile.location
    series = await aq_client.get_hourly_forecast(lat=loc.lat, lng=loc.lng, hours=24)
    pm25_series = [pt.pm25_ug_m3 for pt in series.points]
    result = compute_family_passbook(req.profile, pm25_series)
    meta = make_meta(request, data_mode=series.data_mode)
    return Envelope(data=asdict(result), meta=meta)


@api_router.post("/indoor/simulate", response_model=Envelope[dict[str, Any]], tags=["indoor"])
async def post_indoor_simulate(
    req: IndoorSimulateRequest,
    request: Request,
    aq_client: AqClientDep,
) -> Envelope[dict[str, Any]]:
    """Simulate 24-hour indoor PM2.5, evaluate purifier, and rank hacks."""
    loc = req.location
    series = await aq_client.get_hourly_forecast(lat=loc.lat, lng=loc.lng, hours=24)
    pm25_series = [pt.pm25_ug_m3 for pt in series.points]
    result = simulate_indoor_environment(
        room=req.room,
        sources=req.sources,
        outdoor_pm25_series=pm25_series,
    )
    meta = make_meta(request, data_mode=series.data_mode)
    return Envelope(data=asdict(result), meta=meta)


@api_router.post("/plan", response_model=Envelope[dict[str, Any]], tags=["plan"])
async def post_plan(
    req: PlanRequest,
    request: Request,
    aq_client: AqClientDep,
) -> Envelope[dict[str, Any]]:
    """Optimise member routines into clean forecast windows."""
    loc = req.profile.location
    series = await aq_client.get_hourly_forecast(lat=loc.lat, lng=loc.lng, hours=24)
    pm25_series = [pt.pm25_ug_m3 for pt in series.points]
    result = compute_optimized_plan(
        profile=req.profile,
        member_id=req.member_id,
        flexible_activities=req.flexible_activities,
        outdoor_pm25_series=pm25_series,
    )
    meta = make_meta(request, data_mode=series.data_mode)
    return Envelope(data=asdict(result), meta=meta)


@api_router.get("/swaps/catalogue", response_model=Envelope[dict[str, Any]], tags=["swaps"])
async def get_swaps_catalogue(request: Request) -> Envelope[dict[str, Any]]:
    """Retrieve list of available sustainable lifestyle swaps."""
    swaps = list_available_swaps()
    meta = make_meta(request, data_mode="fixture")
    return Envelope(data={"swaps": swaps}, meta=meta)


@api_router.post("/swaps/impact", response_model=Envelope[dict[str, Any]], tags=["swaps"])
async def post_swaps_impact(
    req: SwapsImpactRequest,
    request: Request,
    aq_client: AqClientDep,
) -> Envelope[dict[str, Any]]:
    """Evaluate emission reduction and community scaling for a lifestyle swap."""
    data_mode: Literal["live", "fixture"] = "fixture"
    mean_pm25 = 150.0
    if req.location:
        series = await aq_client.get_hourly_forecast(
            lat=req.location.lat, lng=req.location.lng, hours=24
        )
        mean_pm25 = sum(pt.pm25_ug_m3 for pt in series.points) / max(1, len(series.points))
        data_mode = series.data_mode

    result = compute_swap_impact(req, outdoor_pm25_mean=mean_pm25)
    meta = make_meta(request, data_mode=data_mode)
    return Envelope(data=asdict(result), meta=meta)
