"""FastAPI application factory: wiring only, no business logic."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hawakhata import version
from hawakhata.agent.prompts import list_prompts, load_prompt
from hawakhata.agent.sessions import build_session_store
from hawakhata.api.dependencies import get_aq_client
from hawakhata.api.routes import api_router, system_router
from hawakhata.config import Settings, get_settings
from hawakhata.core.cache import build_cache, build_redis_client
from hawakhata.core.errors import register_exception_handlers
from hawakhata.core.logging import configure_logging
from hawakhata.core.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from hawakhata.core.rate_limit import build_rate_limiter
from hawakhata.engine.cities import get_supported_cities

if TYPE_CHECKING:
    from redis.asyncio import Redis


def create_app(settings: Settings | None = None, *, redis_client: Redis | None = None) -> FastAPI:
    """Build the app with middleware, shared clients and system routes.

    With REDIS_URL set (or ``redis_client`` injected) the AQ cache, chat sessions and rate-limit
    buckets live in Redis and are shared by every instance; each degrades to in-memory on a
    transient Redis error. Without it everything is bounded in-memory.
    """
    cfg = settings or get_settings()
    configure_logging(cfg.log_level, cfg.gcp_project_id)
    owns_redis = redis_client is None
    redis = redis_client or build_redis_client(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.http = httpx.AsyncClient(timeout=cfg.aq_timeout_s)
        try:
            yield
        finally:
            await app.state.http.aclose()
            if redis is not None and owns_redis:
                await redis.aclose()

    app = FastAPI(
        title="HawaKhata API",
        version=version.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs" if cfg.app_env != "prod" else None,
        redoc_url=None,
    )
    app.state.settings = cfg
    app.state.redis = redis
    app.state.cache = build_cache(cfg, redis)
    app.state.sessions = build_session_store(cfg, redis)

    # GZip innermost: it must see the whole body for minimum_size to apply (outer
    # BaseHTTPMiddleware layers re-stream responses in chunks).
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=build_rate_limiter(cfg, redis),
        trusted_proxy_hops=cfg.trusted_proxy_hops,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=cfg.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(system_router)

    root_dir = Path(__file__).resolve().parent.parent.parent
    static_dir = root_dir / "static"
    templates_dir = root_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    templates = Jinja2Templates(directory=templates_dir) if templates_dir.exists() else None

    @app.get("/", response_class=HTMLResponse, tags=["web"])
    async def index_page(request: Request) -> HTMLResponse:
        return (
            templates.TemplateResponse(request=request, name="index.html")
            if templates
            else HTMLResponse("<h1>HawaKhata</h1>")
        )

    @app.get("/how-it-works", response_class=HTMLResponse, tags=["web"])
    async def how_it_works_page(request: Request) -> HTMLResponse:
        return (
            templates.TemplateResponse(request=request, name="how_it_works.html")
            if templates
            else HTMLResponse("<h1>How HawaKhata Works</h1>")
        )

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        """Liveness: zero dependencies, so an upstream blip never restarts a healthy container."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    async def readyz() -> JSONResponse:
        """Readiness: internal dependencies only — never calls Open-Meteo, Google AQ or Gemini."""
        checks = {"config": "ok" if app.state.settings is cfg else "fail", "redis": "skipped"}
        try:
            load_prompt("agent_system")
            checks["prompts"] = "ok" if list_prompts() else "fail"
        except (OSError, ValueError):
            checks["prompts"] = "fail"
        if app.state.redis is not None:
            try:
                ok = await asyncio.wait_for(app.state.redis.ping(), timeout=1.0)
                checks["redis"] = "ok" if ok else "fail"
            except Exception:  # any Redis/network/timeout error means "not ready"
                checks["redis"] = "fail"
        ready = "fail" not in checks.values()
        body = {"status": "ready" if ready else "not_ready", "checks": checks}
        return JSONResponse(body, status_code=200 if ready else 503)

    @app.get("/api/v1/meta", tags=["system"])
    async def meta(request: Request) -> dict[str, object]:
        runtime = {  # read-only operational telemetry; never includes keys or URLs
            "cache_backend": "redis" if app.state.redis is not None else "memory",
            "state_backend": "redis" if app.state.redis is not None else "memory",
            "provider_chain": ["open_meteo_live", "google_aq_live", "fixture"],
            "circuit_breakers": get_aq_client(request).breaker_states(),
            "grounding_gate": True,
            "rate_limit_enabled": True,
        }
        return {
            "data": {
                "app_version": version.APP_VERSION,
                "engine_version": version.ENGINE_VERSION,
                "agent_version": version.AGENT_VERSION,
                "prompt_version": version.PROMPT_VERSION,
                "constants_version": version.CONSTANTS_VERSION,
                "data_mode": "live" if cfg.has_live_air_data else "fixture",
                "llm_mode": "gemini" if cfg.has_llm else "deterministic",
                "story_mode_clock": cfg.demo_clock_iso,
                "cities": [
                    {"id": c.id, "name": c.name, "lat": c.lat, "lng": c.lng, "state": c.state}
                    for c in get_supported_cities()
                ],
                "runtime": runtime,
            }
        }

    return app
