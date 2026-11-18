"""FastAPI dependencies providing settings, caching, clients, and response envelopes."""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import Request

from hawakhata import version
from hawakhata.api.schemas import ResponseMeta
from hawakhata.config import Settings
from hawakhata.core.cache import CacheBackend
from hawakhata.integrations.air_quality import AirQualityClient


def get_settings(request: Request) -> Settings:
    """Extract singleton application configuration from request app state."""
    cfg: Settings = request.app.state.settings
    return cfg


def get_cache(request: Request) -> CacheBackend:
    """Extract shared cache backend from request app state."""
    cache: CacheBackend = request.app.state.cache
    return cache


def get_aq_client(request: Request) -> AirQualityClient:
    """Construct or retrieve the AirQualityClient with shared httpx client and cache."""
    client = getattr(request.app.state, "aq_client", None)
    if client is None:
        http_client = getattr(request.app.state, "http", None)
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=request.app.state.settings.aq_timeout_s)
            request.app.state.http = http_client
        client = AirQualityClient(
            settings=request.app.state.settings,
            cache=request.app.state.cache,
            http_client=http_client,
        )
        request.app.state.aq_client = client
    return client


def make_meta(
    request: Request,
    data_mode: Literal["live", "fixture"],
    degraded: bool = False,
) -> ResponseMeta:
    """Construct unified response metadata carrying the request ID and version numbers."""
    req_id = getattr(request.state, "request_id", "req-local")
    return ResponseMeta(
        request_id=req_id,
        data_mode=data_mode,
        engine_version=version.ENGINE_VERSION,
        constants_version=version.CONSTANTS_VERSION,
        prompt_version=version.PROMPT_VERSION,
        agent_version=version.AGENT_VERSION,
        degraded=degraded,
    )
