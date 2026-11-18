"""FastAPI router mounting all HawaKhata REST computing and data endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request

from hawakhata.api.dependencies import get_aq_client, make_meta
from hawakhata.api.schemas import (
    BriefAction,
    BriefRequest,
    BriefResponse,
    Envelope,
    ForecastRequest,
    IndoorSimulateRequest,
    PassbookRequest,
    PlanRequest,
    SensitiveAlert,
    SwapsImpactRequest,
)
from hawakhata.config import get_settings
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.services.brief_service import generate_morning_brief
from hawakhata.services.indoor_service import simulate_indoor_environment
from hawakhata.services.passbook_service import compute_family_passbook
from hawakhata.services.planner_service import compute_optimized_plan
from hawakhata.services.story_service import load_demo_profiles, load_story
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


@api_router.post("/brief", response_model=Envelope[BriefResponse], tags=["brief"])
async def post_morning_brief(
    req: BriefRequest,
    request: Request,
    aq_client: AqClientDep,
) -> Envelope[BriefResponse]:
    """Generate proactive morning brief with forecast-shift detection and recommendations."""
    lat, lng = 28.459, 77.026
    if req.profile.location:
        lat, lng = req.profile.location.lat, req.profile.location.lng
    series = await aq_client.get_hourly_forecast(lat=lat, lng=lng, hours=24)
    brief = generate_morning_brief(
        profile=req.profile,
        air_series=series,
        cached_yesterday_series=req.previous_forecast_pm25,
        threshold_ug_m3=get_settings().forecast_shift_replan_threshold_ug_m3,
    )
    meta = make_meta(request, data_mode=series.data_mode)
    data = BriefResponse(
        headline=brief.headline,
        worst_hour_local=brief.worst_hour_local,
        worst_pm25=brief.worst_pm25,
        cleanest_window_local=brief.cleanest_window_local,
        cleanest_pm25=brief.cleanest_pm25,
        sensitive_member_alerts=[
            SensitiveAlert(**asdict(a)) for a in brief.sensitive_member_alerts
        ],
        top_actions=[BriefAction(**asdict(a)) for a in brief.top_actions],
        forecast_shift=brief.forecast_shift,
        explanation=brief.explanation.to_dict(),
    )
    return Envelope(data=data, meta=meta)


@api_router.get("/demo/profiles", response_model=Envelope[dict[str, Any]], tags=["demo"])
async def get_demo_profiles(request: Request) -> Envelope[dict[str, Any]]:
    """Return pre-configured demo family profiles from fixtures."""
    profiles = load_demo_profiles()
    meta = make_meta(request, data_mode="fixture")
    return Envelope(data=profiles, meta=meta)


@api_router.get("/story/{story_id}", response_model=Envelope[dict[str, Any]], tags=["story"])
async def get_story_tour(story_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Retrieve narrative steps and fixed clock metadata for story mode tour."""
    story_data = load_story(story_id)
    meta = make_meta(request, data_mode="fixture")
    return Envelope(data=story_data, meta=meta)
