"""HTTP middleware: request ids, security + cache headers, body-size limit, rate limiting."""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from hawakhata.core.errors import ErrorCode, error_body
from hawakhata.core.logging import bind_request_id, get_logger

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
NO_STORE_PATHS = ("/api/v1/chat",)


def cache_control_for(path: str) -> str | None:
    """Cache policy: static assets cache for 1 h; chat turns are never stored."""
    if path.startswith("/static/"):
        return STATIC_CACHE_CONTROL
    if path.startswith(NO_STORE_PATHS):
        return "no-store"
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, expose it as X-Request-ID and log latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        is_safe_id = 8 <= len(incoming) <= 64 and incoming.isalnum()  # noqa: PLR2004
        request_id = incoming if is_safe_id else uuid.uuid4().hex
        bind_request_id(request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        _log.info(
            "request",
            extra={
                "route": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
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
    """Apply the token-bucket limiter to /api/ routes."""

    def __init__(self, app: ASGIApp, limiter: TokenBucketLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        client = self._limiter.client_key(request.client.host if request.client else "unknown")
        if not self._limiter.allow(client):
            headers = {"Retry-After": str(self._limiter.retry_after_s(client))}
            return JSONResponse(
                error_body(ErrorCode.RATE_LIMITED, "Too many requests.", retryable=True),
                status_code=429,
                headers=headers,
            )
        return await call_next(request)
