"""HTTP middleware: request ids, security + cache headers, body-size limit, rate limiting."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.routing import Match

from hawakhata.core.errors import ErrorCode, error_body
from hawakhata.core.logging import (
    bind_request_id,
    bind_trace,
    get_logger,
    parse_cloud_trace_context,
)
from hawakhata.core.metrics import HTTP_DURATION, HTTP_REQUESTS, RATE_LIMIT_REJECTIONS
from hawakhata.core.rate_limit import resolve_client_ip

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

    from hawakhata.core.rate_limit import TokenBucketLimiter

_log = get_logger(__name__)

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)
SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


STATIC_CACHE_CONTROL = "public, max-age=3600"
NO_STORE_PATHS = ("/api/v1/chat", "/metrics", "/readyz")


def cache_control_for(path: str) -> str | None:
    """Cache policy: static assets cache for 1 h; chat turns are never stored."""
    if path.startswith("/static/"):
        return STATIC_CACHE_CONTROL
    if path.startswith(NO_STORE_PATHS):
        return "no-store"
    return None


def route_label(request: Request) -> str:
    """Bounded metric label: a route template, never the raw (high-cardinality) path.

    Called before routing (Mounts rewrite root_path while routing); paths of routes resolved
    during routing are preferred via ``scope["route"]`` in RequestContextMiddleware.
    """
    for route in request.app.router.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and route.matches(request.scope)[0] != Match.NONE:
            return path
    return "unmatched"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id + Cloud Trace context, log latency and record HTTP metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        is_safe_id = 8 <= len(incoming) <= 64 and incoming.isalnum()  # noqa: PLR2004
        request_id = incoming if is_safe_id else uuid.uuid4().hex
        bind_request_id(request_id)
        bind_trace(parse_cloud_trace_context(request.headers.get("x-cloud-trace-context")))
        pre_route = route_label(request)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        response.headers["X-Request-ID"] = request_id
        route = getattr(request.scope.get("route"), "path", None) or pre_route
        labels = {"route": str(route), "status": str(response.status_code)}
        HTTP_REQUESTS.inc(**labels)
        HTTP_DURATION.observe(elapsed, **labels)
        _log.info(
            "request",
            extra={
                "route": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": round(elapsed * 1000, 1),
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach CSP, hardening and Cache-Control headers; HSTS only when served over HTTPS."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        cache_control = cache_control_for(request.url.path)
        if cache_control:
            response.headers["Cache-Control"] = cache_control
        if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body exceeds max_body_bytes."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        declared = request.headers.get("content-length")
        too_large = declared is not None and (
            not declared.isdigit() or int(declared) > self._max_body_bytes
        )
        if too_large:
            return JSONResponse(
                error_body(ErrorCode.PAYLOAD_TOO_LARGE, "Request body is too large."),
                status_code=413,
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply the token-bucket limiter to /api/ routes, keyed on the spoof-proof client IP."""

    def __init__(
        self, app: ASGIApp, limiter: TokenBucketLimiter, trusted_proxy_hops: int = 1
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._hops = trusted_proxy_hops

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        client_ip = resolve_client_ip(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
            self._hops,
        )
        request.state.client_ip = client_ip
        client = self._limiter.client_key(client_ip)
        if not self._limiter.allow(client):
            RATE_LIMIT_REJECTIONS.inc()
            headers = {"Retry-After": str(self._limiter.retry_after_s(client))}
            return JSONResponse(
                error_body(ErrorCode.RATE_LIMITED, "Too many requests.", retryable=True),
                status_code=429,
                headers=headers,
            )
        return await call_next(request)
