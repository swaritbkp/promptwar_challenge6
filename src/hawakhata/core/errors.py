"""Domain exceptions and the single JSON error contract returned by the API."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from hawakhata.core.logging import current_request_id, get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

_log = get_logger(__name__)


class ErrorCode(StrEnum):
    """Stable, documented error codes."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for errors that map cleanly onto the API error contract."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = 500
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailedError(AppError):
    code, status_code = ErrorCode.VALIDATION_ERROR, 422


class NotFoundError(AppError):
    code, status_code = ErrorCode.NOT_FOUND, 404


class UpstreamUnavailableError(AppError):
    code, status_code, retryable = ErrorCode.UPSTREAM_ERROR, 503, True


class RateLimitedError(AppError):
    code, status_code, retryable = ErrorCode.RATE_LIMITED, 429, True


class GuardrailBlockedError(AppError):
    code, status_code = ErrorCode.GUARDRAIL_BLOCKED, 400


def error_body(code: ErrorCode, message: str, *, retryable: bool = False) -> dict[str, object]:
    """Build the error envelope, attaching the current request id."""
    return {
        "error": {
            "code": code.value,
            "message": message,
            "request_id": current_request_id(),
            "retryable": retryable,
        }
    }


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101
    _log.warning("app_error", extra={"code": exc.code.value})
    return JSONResponse(
        error_body(exc.code, exc.message, retryable=exc.retryable), status_code=exc.status_code
    )


async def _handle_validation(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    fields = [".".join(str(p) for p in err.get("loc", ())) for err in exc.errors()][:10]
    message = "Invalid request: " + ", ".join(fields) if fields else "Invalid request"
    return JSONResponse(error_body(ErrorCode.VALIDATION_ERROR, message), status_code=422)


async def _handle_http(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INTERNAL_ERROR  # noqa: PLR2004
    return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    _log.exception("unhandled_error", extra={"error_type": type(exc).__name__})
    return JSONResponse(
        error_body(ErrorCode.INTERNAL_ERROR, "Something went wrong. Please try again."),
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers so every failure follows the error contract."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http)
    app.add_exception_handler(Exception, _handle_unexpected)
