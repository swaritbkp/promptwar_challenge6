"""Structured JSON logging compatible with Google Cloud Logging.

Log records never contain user text, prompts, API keys or exact coordinates —
only identifiers, codes and measurements.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_trace: ContextVar[tuple[str, str] | None] = ContextVar("trace", default=None)
_project = {"id": ""}
_CLOUD_TRACE = re.compile(r"^([0-9a-fA-F]{32})(?:/(\d{1,20}))?(?:;o=[01])?$")
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


def current_request_id() -> str:
    """Return the request id bound to the current async context."""
    return _request_id.get()


def bind_request_id(request_id: str) -> None:
    """Bind ``request_id`` to the current async context."""
    _request_id.set(request_id)


def parse_cloud_trace_context(header: str | None) -> tuple[str, str] | None:
    """Parse ``X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=1`` into (trace_id, span_id)."""
    match = _CLOUD_TRACE.match((header or "").strip())
    return (match.group(1).lower(), match.group(2) or "") if match else None


def bind_trace(trace: tuple[str, str] | None) -> None:
    """Bind a parsed Cloud Trace context (or None) to the current async context."""
    _trace.set(trace)


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
        trace = _trace.get()
        if trace:
            payload["trace_id"] = trace[0]
            if _project["id"]:
                payload["logging.googleapis.com/trace"] = (
                    f"projects/{_project['id']}/traces/{trace[0]}"
                )
                if trace[1]:
                    payload["logging.googleapis.com/spanId"] = trace[1]
        payload.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, gcp_project_id: str | None = None) -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    _project["id"] = gcp_project_id or ""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Return a module logger."""
    return logging.getLogger(name)
