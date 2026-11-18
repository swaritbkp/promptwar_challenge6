"""FastAPI application factory: wiring only, no business logic.

Run locally::

    uvicorn hawakhata.app:create_app --factory --app-dir src --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hawakhata import version
from hawakhata.api.routes import api_router
from hawakhata.config import Settings, get_settings
from hawakhata.core.cache import build_cache
from hawakhata.core.errors import register_exception_handlers
from hawakhata.core.logging import configure_logging
from hawakhata.core.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from hawakhata.core.rate_limit import TokenBucketLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app with middleware, shared clients and system routes.

    Args:
        settings: Optional explicit settings (tests); defaults to :func:`get_settings`.

    Returns:
        A configured :class:`FastAPI` instance.
    """
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.http = httpx.AsyncClient(timeout=cfg.aq_timeout_s)
        try:
            yield
        finally:
            await app.state.http.aclose()

    app = FastAPI(
        title="HawaKhata API",
        version=version.APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs" if cfg.app_env != "prod" else None,
        redoc_url=None,
    )
    app.state.settings = cfg
    app.state.cache = build_cache(cfg)

    # Starlette runs the LAST added middleware first, so add innermost first.
    app.add_middleware(
        RateLimitMiddleware,
        limiter=TokenBucketLimiter(cfg.rate_limit_per_min, cfg.rate_limit_max_clients),
    )
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=cfg.max_body_bytes)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)

    root_dir = Path(__file__).resolve().parent.parent.parent
    static_dir = root_dir / "static"
    templates_dir = root_dir / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    templates = Jinja2Templates(directory=templates_dir) if templates_dir.exists() else None

    @app.get("/", response_class=HTMLResponse, tags=["web"])
    async def index_page(request: Request) -> HTMLResponse:
        """Render HawaKhata single-page application shell."""
        if templates is None:
            return HTMLResponse("<h1>HawaKhata</h1>")
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/how-it-works", response_class=HTMLResponse, tags=["web"])
    async def how_it_works_page(request: Request) -> HTMLResponse:
        """Render trust, science and verified constants page."""
        if templates is None:
            return HTMLResponse("<h1>How HawaKhata Works</h1>")
        return templates.TemplateResponse(request=request, name="how_it_works.html")

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        """Liveness probe; never calls upstream services."""
        return {"status": "ok"}

    @app.get("/api/v1/meta", tags=["system"])
    async def meta() -> dict[str, object]:
        """Report versions and whether live Google data / Gemini are configured."""
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
            }
        }

    return app
