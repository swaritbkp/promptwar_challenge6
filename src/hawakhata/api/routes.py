"""FastAPI router mounting all HawaKhata REST computing and data endpoints."""

from __future__ import annotations

import asyncio
import hmac
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from hawakhata.agent.agent import HawaKhataAgent
from hawakhata.api.dependencies import (
    get_agent,
    get_aq_client,
    get_geo_client,
    get_weather_client,
    make_meta,
)
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
    LocationResult,
    MaskedActivityRequest,
    MemberInput,
    PassbookRequest,
    PetGuidanceRequest,
    PlanRequest,
    SensitiveAlert,
    SwapsImpactRequest,
    WeatherSummary,
)
from hawakhata.config import get_settings
from hawakhata.core.errors import ErrorCode, error_body
from hawakhata.core.logging import get_logger
from hawakhata.core.metrics import TurnTelemetry, render_prometheus
from hawakhata.engine.aqi import aqi_to_grap_stage, compute_live_aq_snapshot
from hawakhata.engine.budget import daily_air_budget_ug
from hawakhata.engine.dose import compute_masked_activity_dose
from hawakhata.engine.pets import evaluate_pet_walk_risk, get_indoor_pet_guidance
from hawakhata.engine.planner import (
    align_to_clock,
    build_four_day_outlook,
    classify_dispersion,
    optimize_multi_day_activity,
    summarize_day_parts,
)
from hawakhata.integrations.air_quality import (
    AirQualityClient,
    HourlyAirSeries,
    clock_aligned_pm25,
)
from hawakhata.integrations.geocoding import GeocodingClient
from hawakhata.integrations.weather import WeatherClient
from hawakhata.services.brief_service import generate_morning_brief
from hawakhata.services.indoor_service import simulate_indoor_environment
from hawakhata.services.passbook_service import (
    compute_family_passbook,
    generate_shareable_digest,
    rank_household_triage,
)
from hawakhata.services.planner_service import compute_optimized_plan
from hawakhata.services.story_service import load_demo_profiles, load_personas, load_story
from hawakhata.services.swap_service import compute_swap_impact, list_available_swaps

api_router = APIRouter(prefix="/api/v1")
system_router = APIRouter(tags=["system"])
_log = get_logger(__name__)


@system_router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(request: Request) -> Response:
    """Prometheus scrape target: bounded-label counters/histograms only (no PII, prompts, keys).

    With METRICS_AUTH_TOKEN set, a constant-time bearer check guards it; failures say nothing
    about the expected token.
    """
    token = request.app.state.settings.metrics_auth_token
    if token is not None:
        expected = f"Bearer {token.get_secret_value()}".encode()
        provided = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(provided, expected):
            return JSONResponse(
                error_body(ErrorCode.UNAUTHORIZED, "Authentication required."),
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


AqClientDep = Annotated[AirQualityClient, Depends(get_aq_client)]
WeatherClientDep = Annotated[WeatherClient, Depends(get_weather_client)]
AgentDep = Annotated[HawaKhataAgent, Depends(get_agent)]
GeoClientDep = Annotated[GeocodingClient, Depends(get_geo_client)]
# Letters/marks in any script (Devanagari included), digits, space and . , ' ( ) - only.
_PLACE_QUERY = r"^[\p{L}\p{M}\p{N} .,'()-]{2,60}$"


async def _get_series(
    client: AirQualityClient, loc: LocationInput
) -> tuple[HourlyAirSeries, list[float]]:
    """24h series + PM2.5 re-indexed so position h is clock hour h (engine convention)."""
    s = await client.get_hourly_forecast(lat=loc.lat, lng=loc.lng, hours=24)
    return s, clock_aligned_pm25(s)


def _aq_snapshot(s: HourlyAirSeries) -> dict[str, Any]:
    """Live-now snapshot shared by passbook and 4-day views (single source of truth)."""
    first = s.points[0] if s.points else None
    cur_pm, cur_aqi, code, label = compute_live_aq_snapshot(first.pm25_ug_m3 if first else 150.0)
    return {
        "current_pm25": cur_pm,
        "current_pm10": first.pm10_ug_m3 if first else None,
        "current_aqi": cur_aqi,
        "current_category": code,
        "current_category_label": label,
        "data_mode": s.provider,
        "data_source": s.data_source,
        "fetched_at_ist": s.fetched_at_ist,
        "grap": aqi_to_grap_stage(cur_aqi),
    }


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
    aq_series, weather_series = await asyncio.gather(
        aq_client.get_hourly_forecast(lat=lat, lng=resolved_lng, hours=96),
        weather_client.get_hourly_weather(lat=lat, lng=resolved_lng, hours=96),
    )
    hourly_pm25 = [p.pm25_ug_m3 for p in aq_series.points]
    synthetic, start_hour = aq_series.data_mode == "fixture", aq_series.start_hour
    outlook = build_four_day_outlook(
        hourly_pm25, weather_series.points, synthetic=synthetic, start_hour=start_hour
    )
    top_slots = optimize_multi_day_activity(
        age_band=age_band,
        activity_type=activity,
        duration_min=duration_min,
        hourly_pm25=hourly_pm25,
        hourly_weather=weather_series.points,
        synthetic=synthetic,
        start_hour=start_hour,
    )
    clock_24h = clock_aligned_pm25(aq_series, 24)

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
        **_aq_snapshot(aq_series),
        day_parts=summarize_day_parts(clock_24h),
        hourly_pm25_24h=clock_24h,
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
    snap = _aq_snapshot(s)
    snap["grap"] = asdict(snap["grap"])
    return Envelope(data={**asdict(res), **snap}, meta=make_meta(request, data_mode=s.data_mode))


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
    tel = TurnTelemetry("brief_turn")
    lat, lng = (
        (req.profile.location.lat, req.profile.location.lng)
        if req.profile.location
        else (28.459, 77.026)
    )
    with tel.stage("aq"):
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
    return tel.finish(Envelope(data=data, meta=make_meta(request, data_mode=s.data_mode)))


@api_router.get("/demo/profiles", response_model=Envelope[dict[str, Any]], tags=["demo"])
async def get_demo_profiles(request: Request) -> Envelope[dict[str, Any]]:
    """Return pre-configured demo family profiles from fixtures."""
    return Envelope(data=load_demo_profiles(), meta=make_meta(request, data_mode="fixture"))


@api_router.get("/demo/personas", response_model=Envelope[dict[str, Any]], tags=["demo"])
async def get_demo_personas(request: Request) -> Envelope[dict[str, Any]]:
    """Return the 4 Quick Scenario personas (Delhi, Mumbai, Kolkata, Chandigarh)."""
    return Envelope(
        data={"personas": load_personas()}, meta=make_meta(request, data_mode="fixture")
    )


@api_router.get("/story/{story_id}", response_model=Envelope[dict[str, Any]], tags=["story"])
async def get_story_tour(story_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Retrieve narrative steps and fixed clock metadata for story mode tour."""
    return Envelope(data=load_story(story_id), meta=make_meta(request, data_mode="fixture"))


@api_router.post("/pets/guidance", response_model=Envelope[dict[str, Any]], tags=["pets"])
async def post_pet_guidance(
    req: PetGuidanceRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Determine safe pet walk duration and species-specific indoor guidance."""
    s, _ = await _get_series(aq_client, req.location)
    cur_pm = s.points[0].pm25_ug_m3 if s.points else 150.0
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
    pts = align_to_clock(s.points, s.start_hour)[: len(s.points)]
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


@api_router.post("/exposure/activity", response_model=Envelope[dict[str, Any]], tags=["plan"])
async def post_masked_activity(
    req: MaskedActivityRequest, request: Request, aq_client: AqClientDep
) -> Envelope[dict[str, Any]]:
    """Outdoor activity dose with a mask (none / surgical / N95) vs the member's WHO budget."""
    s, pm25 = await _get_series(aq_client, req.location)
    hours = max(1, -(-req.duration_min // 60))
    window = [pm25[(req.start_hour + i) % len(pm25)] for i in range(hours)] if pm25 else [150.0]
    res = compute_masked_activity_dose(
        req.age_band,
        req.activity,
        window,
        req.duration_min,
        req.mask,
        daily_air_budget_ug(req.age_band),
    )
    data = asdict(res)
    data["explanation"] = res.explanation.to_dict()
    data["start_hour"] = req.start_hour
    return Envelope(data=data, meta=make_meta(request, data_mode=s.data_mode))


@api_router.get(
    "/locations/search", response_model=Envelope[list[LocationResult]], tags=["locations"]
)
async def search_locations(
    request: Request,
    geo_client: GeoClientDep,
    q: Annotated[str, Query(min_length=2, max_length=60, pattern=_PLACE_QUERY)],
) -> Envelope[list[LocationResult]]:
    """Search any Indian city or town (server-side Open-Meteo Geocoding proxy)."""
    places = await geo_client.search(q)
    live = any(p.source != "builtin" for p in places)
    return Envelope(
        data=[LocationResult(**asdict(p)) for p in places],
        meta=make_meta(request, data_mode="live" if live else "fixture"),
    )


def _default_profile() -> FamilyProfileInput:
    return FamilyProfileInput(
        id="fam_default",
        name="Household",
        location=LocationInput(lat=28.4595, lng=77.0266),
        members=[MemberInput(id="m1", name="Family Member", age_band="31_41")],
    )


async def _run_chat(
    req: ChatRequest,
    request: Request,
    agent: HawaKhataAgent,
    aq_client: AirQualityClient,
    on_stage: Callable[[str], None] | None = None,
) -> Envelope[ChatResponse]:
    """One grounded chat turn shared by the JSON and SSE endpoints (identical response schema)."""
    client_ip = str(getattr(request.state, "client_ip", "unknown"))  # set by RateLimitMiddleware
    session_id = req.session_id or f"sess_{uuid.uuid4().hex[:12]}"
    profile = req.profile or _default_profile()
    if req.location is not None:
        profile = profile.model_copy(update={"location": req.location})
    date_iso = (req.now or get_settings().demo_clock_iso or "2026-11-18")[:10]

    result = await agent.run_turn(
        session_id=session_id,
        user_message=req.message,
        profile=profile,
        location=profile.location,
        aq_client=aq_client,
        client_ip=client_ip,
        date_iso=date_iso,
        on_stage=on_stage,
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
        blocked_by_guardrail=result.guardrail is not None,
        guardrail=result.guardrail,
    )
    return Envelope(
        data=data,
        meta=make_meta(
            request,
            data_mode="fixture" if result.fallback_used else "live",
            degraded=result.fallback_used,
        ),
    )


@api_router.post("/chat", response_model=Envelope[ChatResponse], tags=["chat"])
async def post_chat(
    req: ChatRequest, request: Request, agent: AgentDep, aq_client: AqClientDep
) -> Envelope[ChatResponse]:
    """Execute conversational turn with tools, grounding gate, and fallback."""
    return await _run_chat(req, request, agent, aq_client)


STAGE_LABELS = {
    "aq": "Fetching live air quality...",
    "gemini": "Drafting grounded guidance...",
    "grounding": "Verifying every number...",
}
SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


def _sse(event: str, payload: str) -> str:
    return f"event: {event}\ndata: {payload}\n\n"


@api_router.post("/chat/stream", response_class=StreamingResponse, tags=["chat"])
async def post_chat_stream(
    req: ChatRequest, request: Request, agent: AgentDep, aq_client: AqClientDep
) -> StreamingResponse:
    """Same turn as POST /chat, as Server-Sent Events: ``stage`` x N, ``final``, ``done``.

    Grounding-safe: stage events carry only fixed labels; model text leaves solely inside the
    ``final`` envelope, after the grounding gate and output policy have run.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def on_stage(stage: str) -> None:
        body = {"stage": stage, "label": STAGE_LABELS.get(stage, stage)}
        queue.put_nowait(_sse("stage", json.dumps(body)))

    async def events() -> AsyncIterator[str]:
        task = asyncio.create_task(_run_chat(req, request, agent, aq_client, on_stage))
        task.add_done_callback(lambda _: queue.put_nowait(None))
        try:
            while (item := await queue.get()) is not None:
                yield item
            try:
                yield _sse("final", (await task).model_dump_json())
            except Exception as exc:  # never hang or leak internals: typed error, then done
                _log.error("chat_stream_failed", extra={"error": type(exc).__name__})
                err = error_body(ErrorCode.INTERNAL_ERROR, "Chat turn failed.", retryable=True)
                yield _sse("error", json.dumps(err))
            yield _sse("done", "{}")
        finally:
            if not task.done():  # client went away mid-turn
                task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream", headers=SSE_HEADERS)
