"""Structured JSON logging with a trace_id on every line.

The trace_id is the spine of this system: it is minted when a request arrives,
returned to the caller, stored on the document, carried as a Pub/Sub message
attribute, and re-adopted by the worker. One Cloud Logging query on a trace_id
should show the whole journey across services.

Nothing in this codebase calls `print`.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from typing import Any

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(trace_id: str | None) -> str:
    """Adopt an incoming trace_id, or mint one when there is none."""
    value = trace_id or new_trace_id()
    _trace_id.set(value)
    return value


def get_trace_id() -> str:
    return _trace_id.get()


class JsonFormatter(logging.Formatter):
    """Cloud Logging picks up `severity` and `message` from JSON on stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "trace_id": get_trace_id(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", service: str = "regulens") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger(__name__).info("logging configured", extra={"extra_fields": {"service": service}})


def log(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Log one structured line. Prefer this over bare logger calls so that
    additional fields always land in the JSON payload rather than in the message
    string, where nothing can query them."""
    logger.log(level, message, extra={"extra_fields": fields})
