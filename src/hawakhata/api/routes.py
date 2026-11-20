"""FastAPI router mounting all HawaKhata REST computing and data endpoints."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request

from hawakhata.agent.agent import HawaKhataAgent
from hawakhata.api.dependencies import get_agent, get_aq_client, get_weather_client, make_meta
from hawakhata.api.schemas import (
    BriefAction,
    BriefRequest,
    BriefResponse,
    ChatRequest,
    ChatResponse,
    Envelope,
    FamilyProfileInput,
    ForecastRequest,
    FourDayForecastResponse,
    IndoorSimulateRequest,
    LocationInput,
    MemberInput,
    PassbookRequest,
    PetGuidanceRequest,
    PlanRequest,
    SensitiveAlert,
    SwapsImpactRequest,
    WeatherSummary,
)
from hawakhata.config import get_settings
from hawakhata.engine.pets import evaluate_pet_walk_risk, get_indoor_pet_guidance
from hawakhata.engine.planner import (
    build_four_day_outlook,
    classify_dispersion,
    optimize_multi_day_activity,
)
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.integrations.weather import WeatherClient
from hawakhata.services.brief_service import generate_morning_brief
from hawakhata.services.indoor_service import simulate_indoor_environment
from hawakhata.services.passbook_service import (
    compute_family_passbook,
    generate_shareable_digest,
    rank_household_triage,
)
from hawakhata.services.planner_service import compute_optimized_plan
from hawakhata.services.story_service import load_demo_profiles, load_story
from hawakhata.services.swap_service import compute_swap_impact, list_available_swaps

api_router = APIRouter(prefix="/api/v1")
AqClientDep = Annotated[AirQualityClient, Depends(get_aq_client)]
WeatherClientDep = Annotated[WeatherClient, Depends(get_weather_client)]
AgentDep = Annotated[HawaKhataAgent, Depends(get_agent)]


async def _get_series(client: AirQualityClient, loc: LocationInput) -> tuple[Any, list[float]]:
    s = await client.get_hourly_forecast(lat=loc.lat, lng=loc.lng, hours=24)
    return s, [pt.pm25_ug_m3 for pt in s.points]


@api_router.post("/air/forecast", response_model=Envelope[dict[str, Any]], tags=["air"])
async def get_forecast(
    req: ForecastRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Retrieve 24-96h normalised hourly PM2.5 and AQI series."""
    s = await aq_client.get_hourly_forecast(
        lat=req.lat, lng=req.lng, hours=req.hours, language_code=req.language_code
    )
    return Envelope(data=asdict(s), meta=make_meta(request, data_mode=s.data_mode))


@api_router.get(
    "/forecast/4day", response_model=Envelope[FourDayForecastResponse], tags=["forecast"]
)
async def get_four_day_forecast(
    request: Request,
    aq_client: AqClientDep,
    weather_client: WeatherClientDep,
    lat: float = 28.4595,
    lon: float | None = None,
    lng: float | None = None,
    city: str | None = None,
    activity: str = "walk",
    duration_min: int = 60,
    age_band: str = "31_41",
) -> Envelope[FourDayForecastResponse]:
    """Retrieve 4-day predictive outlook, Tomorrow Watch alert, and multi-day routine slots."""
    resolved_lng = lng if lng is not None else (lon if lon is not None else 77.0266)
    aq_series = await aq_client.get_hourly_forecast(lat=lat, lng=resolved_lng, hours=96)
    weather_series = await weather_client.get_hourly_weather(lat=lat, lng=resolved_lng, hours=96)
    hourly_pm25 = [p.pm25_ug_m3 for p in aq_series.points]
    outlook = build_four_day_outlook(hourly_pm25, weather_series.points)
    top_slots = optimize_multi_day_activity(
        age_band=age_band,
        activity_type=activity,
        duration_min=duration_min,
        hourly_pm25=hourly_pm25,
        hourly_weather=weather_series.points,
    )

    resolved_city = city or ("Chandigarh" if abs(lat - 30.7) < 1.0 else "Delhi NCR")
    curr_w = weather_series.points[0] if weather_series.points else None
    weather_summary: WeatherSummary | None = None
    if curr_w:
        regime, exp = classify_dispersion(
            curr_w.wind_speed_kmh,
            curr_w.boundary_layer_height_m,
            curr_w.relative_humidity_pct,
            curr_w.precipitation_mm,
        )
        weather_summary = WeatherSummary(
            temperature_c=curr_w.temperature_c,
            humidity_pct=curr_w.relative_humidity_pct,
            wind_speed_kmh=curr_w.wind_speed_kmh,
            precipitation_mm=curr_w.precipitation_mm,
            boundary_layer_height_m=curr_w.boundary_layer_height_m,
            dispersion_regime=regime,
            physical_explanation=exp,
        )

    response_data = FourDayForecastResponse(
        city=resolved_city,
        tomorrow_watch_headline=outlook.tomorrow_watch_headline,
        tomorrow_watch_direction=outlook.tomorrow_watch_direction,
        days=outlook.days,
        safe_house_flush=outlook.safe_house_flush,
        top_slots=top_slots,
        current_weather=weather_summary,
    )
    return Envelope(
        data=response_data,
        meta=make_meta(request, data_mode=aq_series.data_mode),
    )


@api_router.post("/passbook", response_model=Envelope[dict[str, Any]], tags=["passbook"])
async def post_passbook(
    req: PassbookRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Compute per-member inhaled dose, daily air budget, and balance."""
    s, pm25 = await _get_series(aq_client, req.profile.location)
    res = compute_family_passbook(req.profile, pm25)
    return Envelope(data=asdict(res), meta=make_meta(request, data_mode=s.data_mode))


@api_router.post("/indoor/simulate", response_model=Envelope[dict[str, Any]], tags=["indoor"])
async def post_indoor_simulate(
    req: IndoorSimulateRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Simulate 24-hour indoor PM2.5, evaluate purifier, and rank hacks."""
    s, pm25 = await _get_series(aq_client, req.location)
    res = simulate_indoor_environment(room=req.room, sources=req.sources, outdoor_pm25_series=pm25)
    return Envelope(data=asdict(res), meta=make_meta(request, data_mode=s.data_mode))


@api_router.post("/plan", response_model=Envelope[dict[str, Any]], tags=["plan"])
async def post_plan(
    req: PlanRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Optimise member routines into clean forecast windows."""
    s, pm25 = await _get_series(aq_client, req.profile.location)
    res = compute_optimized_plan(
        profile=req.profile,
        member_id=req.member_id,
        flexible_activities=req.flexible_activities,
        outdoor_pm25_series=pm25,
    )
    return Envelope(data=asdict(res), meta=make_meta(request, data_mode=s.data_mode))


@api_router.get("/swaps/catalogue", response_model=Envelope[dict[str, Any]], tags=["swaps"])
async def get_swaps_catalogue(request: Request) -> Envelope[dict[str, Any]]:
    """Retrieve list of available sustainable lifestyle swaps."""
    return Envelope(
        data={"swaps": list_available_swaps()}, meta=make_meta(request, data_mode="fixture")
    )


@api_router.post("/swaps/impact", response_model=Envelope[dict[str, Any]], tags=["swaps"])
async def post_swaps_impact(
    req: SwapsImpactRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Evaluate emission reduction and community scaling for a swap."""
    data_mode: Literal["live", "fixture"] = "fixture"
    mean_pm25 = 150.0
    if req.location:
        s = await aq_client.get_hourly_forecast(
            lat=req.location.lat, lng=req.location.lng, hours=24
        )
        mean_pm25 = sum(pt.pm25_ug_m3 for pt in s.points) / max(1, len(s.points))
        data_mode = s.data_mode
    res = compute_swap_impact(req, outdoor_pm25_mean=mean_pm25)
    return Envelope(data=asdict(res), meta=make_meta(request, data_mode=data_mode))


@api_router.post("/brief", response_model=Envelope[BriefResponse], tags=["brief"])
async def post_morning_brief(
    req: BriefRequest, request: Request, aq_client: AqClientDep
) -> Envelope[BriefResponse]:
    """Generate proactive morning brief with forecast-shift detection."""
    lat, lng = (
        (req.profile.location.lat, req.profile.location.lng)
        if req.profile.location
        else (28.459, 77.026)
    )
    s = await aq_client.get_hourly_forecast(lat=lat, lng=lng, hours=24)
    brief = generate_morning_brief(
        profile=req.profile,
        air_series=s,
        cached_yesterday_series=req.previous_forecast_pm25,
        threshold_ug_m3=get_settings().forecast_shift_replan_threshold_ug_m3,
    )
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
    return Envelope(data=data, meta=make_meta(request, data_mode=s.data_mode))


@api_router.get("/demo/profiles", response_model=Envelope[dict[str, Any]], tags=["demo"])
async def get_demo_profiles(request: Request) -> Envelope[dict[str, Any]]:
    """Return pre-configured demo family profiles from fixtures."""
    return Envelope(data=load_demo_profiles(), meta=make_meta(request, data_mode="fixture"))


@api_router.get("/story/{story_id}", response_model=Envelope[dict[str, Any]], tags=["story"])
async def get_story_tour(story_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Retrieve narrative steps and fixed clock metadata for story mode tour."""
    return Envelope(data=load_story(story_id), meta=make_meta(request, data_mode="fixture"))


@api_router.post("/pets/guidance", response_model=Envelope[dict[str, Any]], tags=["pets"])
async def post_pet_guidance(
    req: PetGuidanceRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Determine safe pet walk duration and species-specific indoor guidance."""
    s, pm25_series = await _get_series(aq_client, req.location)
    cur_pm = pm25_series[0] if pm25_series else 150.0
    walk = evaluate_pet_walk_risk(cur_pm)
    indoor = get_indoor_pet_guidance(req.species)
    return Envelope(
        data={
            "species": req.species,
            "current_pm25": cur_pm,
            "safe_walk_duration_min": walk.max_duration_min,
            "pace": walk.pace,
            "post_walk_wipe_needed": walk.post_walk_wipe_needed,
            "walk_advice": walk.summary,
            "walk_instructions": walk.instructions,
            "indoor_vulnerability": indoor.vulnerability_level,
            "airway_mechanisms": indoor.airway_mechanisms,
            "warnings": indoor.warnings,
            "practical_steps": indoor.practical_steps,
        },
        meta=make_meta(request, data_mode=s.data_mode),
    )


@api_router.post("/passbook/triage", response_model=Envelope[dict[str, Any]], tags=["passbook"])
async def post_passbook_triage(
    req: PassbookRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Prioritize family members based on dose burden and vulnerability."""
    s, pm25 = await _get_series(aq_client, req.profile.location)
    pb = compute_family_passbook(req.profile, pm25)
    triage = rank_household_triage(req.profile, pb)
    return Envelope(
        data={
            "family_id": pb.family_id,
            "family_name": pb.family_name,
            "triage": [asdict(i) for i in triage],
        },
        meta=make_meta(request, data_mode=s.data_mode),
    )


@api_router.post("/passbook/digest", response_model=Envelope[dict[str, Any]], tags=["passbook"])
async def post_passbook_digest(
    req: PassbookRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Generate a clean, copy/print-friendly daily passbook summary."""
    s, pm25 = await _get_series(aq_client, req.profile.location)
    pb = compute_family_passbook(req.profile, pm25)
    city = req.profile.location.city_name or "Delhi NCR"
    lang_header = request.headers.get("accept-language", "en")
    lang_code = "hi" if "hi" in lang_header.lower() else "en"
    digest = generate_shareable_digest(req.profile, pb, city_name=city, language=lang_code)
    return Envelope(data={"digest_text": digest}, meta=make_meta(request, data_mode=s.data_mode))


@api_router.post("/air/outlook", response_model=Envelope[dict[str, Any]], tags=["air"])
async def post_air_outlook(
    req: ForecastRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Generate multi-day 96-hour air quality forecast outlook."""
    s = await aq_client.get_hourly_forecast(lat=req.lat, lng=req.lng, hours=min(96, req.hours))
    pts = s.points
    days: list[dict[str, Any]] = []
    for d_idx in range(max(1, len(pts) // 24)):
        chunk = pts[d_idx * 24 : (d_idx + 1) * 24]
        if not chunk:
            continue
        pm_vals = [p.pm25_ug_m3 for p in chunk]
        peak = max(pm_vals)
        mean = sum(pm_vals) / len(pm_vals)
        # Usable daytime waking hours 06:00 to 20:00 (start 06:00 to 17:00 for 3h window)
        daytime_hours = [(h, pm_vals[h]) for h in range(len(pm_vals)) if 6 <= h <= 17]
        if daytime_hours:
            clean_idx, cleanest_pm = min(daytime_hours, key=lambda x: x[1])
        else:
            cleanest_pm = min(pm_vals)
            clean_idx = pm_vals.index(cleanest_pm)
        end_idx = min(20, clean_idx + 3)
        days.append(
            {
                "day_number": d_idx + 1,
                "mean_pm25": round(mean, 1),
                "peak_pm25": round(peak, 1),
                "cleanest_window": f"{clean_idx:02d}:00 - {end_idx:02d}:00",
                "cleanest_pm25": round(cleanest_pm, 1),
                "category": chunk[0].category_local,
            }
        )
    return Envelope(
        data={"days": days, "total_hours": len(pts)}, meta=make_meta(request, data_mode=s.data_mode)
    )


def _default_profile() -> FamilyProfileInput:
    return FamilyProfileInput(
        id="fam_default",
        name="Household",
        location=LocationInput(lat=28.4595, lng=77.0266),
        members=[MemberInput(id="m1", name="Family Member", age_band="31_41")],
    )


@api_router.post("/chat", response_model=Envelope[ChatResponse], tags=["chat"])
async def post_chat(
    req: ChatRequest, request: Request, agent: AgentDep, aq_client: AqClientDep
) -> Envelope[ChatResponse]:
    """Execute conversational turn with tools, grounding gate, and fallback."""
    client_ip = getattr(getattr(request, "client", None), "host", "127.0.0.1")
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    profile = req.profile or _default_profile()
    date_iso = (req.now or get_settings().demo_clock_iso or "2026-11-18")[:10]

    result = await agent.run_turn(
        session_id=session_id,
        user_message=req.message,
        profile=profile,
        location=profile.location,
        aq_client=aq_client,
        client_ip=client_ip,
        date_iso=date_iso,
    )

    data = ChatResponse(
        session_id=session_id,
        reply=result.reply,
        language=result.language,
        numbers_used=result.numbers_used,
        tool_calls=result.tool_calls,
        follow_up=result.follow_up.question if result.follow_up else None,
        chips=result.follow_up.chips if result.follow_up else [],
        grounded=result.grounded,
        degraded=result.fallback_used,
    )
    return Envelope(
        data=data,
        meta=make_meta(
            request,
            data_mode="fixture" if result.fallback_used else "live",
            degraded=result.fallback_used,
        ),
    )
