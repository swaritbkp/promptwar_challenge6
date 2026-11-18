"""Structured JSON logging compatible with Google Cloud Logging.

Log records never contain user text, prompts, API keys or exact coordinates —
only identifiers, codes and measurements.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


def current_request_id() -> str:
    """Return the request id bound to the current async context."""
    return _request_id.get()


def bind_request_id(request_id: str) -> None:
    """Bind ``request_id`` to the current async context."""
    _request_id.set(request_id)


class JsonFormatter(logging.Formatter):
    """Render records as one JSON object per line (``severity`` for Cloud Logging)."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialise the record plus any ``extra=`` fields."""
        payload: dict[str, object] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": current_request_id(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Return a module logger."""
    return logging.getLogger(name)
