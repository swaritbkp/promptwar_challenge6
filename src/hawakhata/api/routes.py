"""FastAPI router mounting all HawaKhata REST computing and data endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from hawakhata.api.dependencies import get_aq_client, make_meta
from hawakhata.api.schemas import (
    Envelope,
    ForecastRequest,
    PassbookRequest,
)
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.services.passbook_service import compute_family_passbook

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
