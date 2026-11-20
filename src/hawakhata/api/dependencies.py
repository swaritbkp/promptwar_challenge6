"""FastAPI dependencies providing settings, caching, clients, and response envelopes."""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import Request

from hawakhata import version
from hawakhata.agent.agent import HawaKhataAgent
from hawakhata.api.schemas import ResponseMeta
from hawakhata.config import Settings
from hawakhata.core.cache import CacheBackend
from hawakhata.integrations.air_quality import AirQualityClient
from hawakhata.integrations.gemini import GeminiCascadeClient
from hawakhata.integrations.geocoding import GeocodingClient
from hawakhata.integrations.weather import WeatherClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_cache(request: Request) -> CacheBackend:
    return request.app.state.cache  # type: ignore[no-any-return]


def _shared_http(request: Request) -> httpx.AsyncClient:
    http_client = getattr(request.app.state, "http", None)
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=request.app.state.settings.aq_timeout_s)
        request.app.state.http = http_client
    return http_client


def get_aq_client(request: Request) -> AirQualityClient:
    client = getattr(request.app.state, "aq_client", None)
    if client is None:
        client = AirQualityClient(
            settings=request.app.state.settings,
            cache=request.app.state.cache,
            http_client=_shared_http(request),
        )
        request.app.state.aq_client = client
    return client


def get_gemini_client(request: Request) -> GeminiCascadeClient:
    client = getattr(request.app.state, "gemini_client", None)
    if client is None:
        client = GeminiCascadeClient(request.app.state.settings)
        request.app.state.gemini_client = client
    return client


def get_weather_client(request: Request) -> WeatherClient:
    client = getattr(request.app.state, "weather_client", None)
    if client is None:
        client = WeatherClient(
            settings=request.app.state.settings,
            cache=request.app.state.cache,
            http_client=_shared_http(request),
        )
        request.app.state.weather_client = client
    return client


def get_geo_client(request: Request) -> GeocodingClient:
    client = getattr(request.app.state, "geo_client", None)
    if client is None:
        client = GeocodingClient(
            settings=request.app.state.settings,
            cache=request.app.state.cache,
            http_client=_shared_http(request),
        )
        request.app.state.geo_client = client
    return client


def get_agent(request: Request) -> HawaKhataAgent:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        agent = HawaKhataAgent(get_gemini_client(request))
        request.app.state.agent = agent
    return agent


def make_meta(
    request: Request, data_mode: Literal["live", "fixture"], degraded: bool = False
) -> ResponseMeta:
    return ResponseMeta(
        request_id=getattr(request.state, "request_id", "req-local"),
        data_mode=data_mode,
        engine_version=version.ENGINE_VERSION,
        constants_version=version.CONSTANTS_VERSION,
        prompt_version=version.PROMPT_VERSION,
        agent_version=version.AGENT_VERSION,
        degraded=degraded,
    )
