"""Central sanitizing layer for application logs.

`PiiSanitizingFilter` and `SanitizingFormatter` are installed on every handler, so any
`logger.*` call (plain text, %-args, dict/DTO arguments, `extra=`, exceptions) is masked
before it is written — individual call sites do not have to remember to do it.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime

from .correlation import correlation_id_var
from .sanitizer import sanitize_text, sanitize_value

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s]: %(message)s"

_STANDARD_ATTRS = frozenset(
    set(logging.makeLogRecord({}).__dict__)
    | {"message", "asctime", "correlation_id", "_pii_sanitized"}
)


def _sanitize_args(args):
    if isinstance(args, dict):
        return sanitize_value(args)
    return tuple(sanitize_value(arg) for arg in args)


def _sanitize_extra(key: str, value):
    cleaned = sanitize_value({key: value})[key]
    if isinstance(cleaned, BaseException):  # keep exception details, minus PII
        return sanitize_text(str(cleaned))
    return cleaned


def _safe_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage()
    except (TypeError, ValueError):
        return str(record.msg)


def _extra_keys(record: logging.LogRecord) -> list[str]:
    return sorted(set(record.__dict__) - _STANDARD_ATTRS)


def sanitize_record(record: logging.LogRecord) -> None:
    """Sanitize a record in place; idempotent so filter + formatter can both call it."""
    record.correlation_id = (
        getattr(record, "correlation_id", None) or correlation_id_var.get() or "-"
    )
    if getattr(record, "_pii_sanitized", False):
        return
    if record.args:
        record.args = _sanitize_args(record.args)
    record.msg = sanitize_text(_safe_message(record))
    record.args = None
    if record.exc_info or record.exc_text:
        raw = record.exc_text or logging.Formatter().formatException(record.exc_info)
        record.exc_text = sanitize_text(raw)
    if record.stack_info:
        record.stack_info = sanitize_text(record.stack_info)
    for key in _extra_keys(record):
        setattr(record, key, _sanitize_extra(key, record.__dict__[key]))
    record._pii_sanitized = True


class PiiSanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        sanitize_record(record)
        return True


class SanitizingFormatter(logging.Formatter):
    def __init__(self, fmt: str = TEXT_FORMAT, **kwargs):
        super().__init__(fmt, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        sanitize_record(record)
        return super().format(record)


class JsonSanitizingFormatter(SanitizingFormatter):
    """One valid JSON object per line; correlation_id and extras stay machine-readable."""

    def format(self, record: logging.LogRecord) -> str:
        sanitize_record(record)
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": record.correlation_id,
            "message": record.getMessage(),
        }
        for key in _extra_keys(record):
            payload[key] = record.__dict__[key]
        if record.exc_text:
            payload["exception"] = record.exc_text
        return json.dumps(payload, default=str, ensure_ascii=False)


def install(handler: logging.Handler, json_format: bool = False) -> logging.Handler:
    handler.addFilter(PiiSanitizingFilter())
    handler.setFormatter(JsonSanitizingFormatter() if json_format else SanitizingFormatter())
    return handler


def configure_logging(level: int = logging.INFO) -> None:
    """Install the sanitizing layer on the root logger (LOG_FORMAT=json|text)."""
    json_format = os.getenv("LOG_FORMAT", "text").lower() == "json"
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stderr))
    for handler in root.handlers:
        if not any(isinstance(f, PiiSanitizingFilter) for f in handler.filters):
            install(handler, json_format)
    for name in ("uvicorn", "uvicorn.error"):
        for handler in logging.getLogger(name).handlers:
            handler.addFilter(PiiSanitizingFilter())
    # Replaced by the body-free access log of CorrelationIdMiddleware.
    logging.getLogger("uvicorn.access").disabled = True
