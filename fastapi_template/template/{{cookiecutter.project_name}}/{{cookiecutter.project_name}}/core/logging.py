"""Production structured logging with request/trace context.

Features:
- JSON logs for production
- human-readable logs for development
- async-safe context propagation
- OpenTelemetry trace correlation
- request/org/user correlation
- structured ``extra=`` fields
- exception serialization
- context-manager helpers
- idempotent configuration
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id",
    default="",
)

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id",
    default="",
)

org_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "org_id",
    default="",
)

user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id",
    default="",
)


def set_trace_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    org_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Set request-scoped logging context."""

    if trace_id is not None:
        trace_id_var.set(trace_id)

    if request_id is not None:
        request_id_var.set(request_id)

    if org_id is not None:
        org_id_var.set(org_id)

    if user_id is not None:
        user_id_var.set(user_id)


def clear_trace_context() -> None:
    """Clear all request-scoped logging context."""

    trace_id_var.set("")
    request_id_var.set("")
    org_id_var.set("")
    user_id_var.set("")


@contextmanager
def trace_context(
    *,
    trace_id: str | None = None,
    request_id: str | None = None,
    org_id: str | None = None,
    user_id: str | None = None,
) -> Iterator[None]:
    """
    Temporarily install logging context.

    Context is restored automatically, making this safer than manually
    clearing ContextVars around nested async operations.
    """

    tokens = []

    values = (
        (trace_id_var, trace_id),
        (request_id_var, request_id),
        (org_id_var, org_id),
        (user_id_var, user_id),
    )

    try:
        for variable, value in values:
            if value is not None:
                tokens.append(
                    variable.set(value)
                )

        yield

    finally:
        for variable, token in reversed(
            list(zip(
                (
                    variable
                    for variable, value in values
                    if value is not None
                ),
                tokens,
            ))
        ):
            variable.reset(token)


def get_trace_id() -> str:
    """Return the current trace ID."""

    return trace_id_var.get()


# ---------------------------------------------------------------------------
# OpenTelemetry
# ---------------------------------------------------------------------------


def _get_otel_trace_id() -> str:
    """Read the current OpenTelemetry trace ID when available."""

    try:
        from opentelemetry import trace

        context = (
            trace.get_current_span()
            .get_span_context()
        )

        if context.is_valid:
            return format(
                context.trace_id,
                "032x",
            )

    except Exception:
        # Logging must never break application execution.
        pass

    return ""


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


_RESERVED_LOG_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


def _json_safe(
    value: Any,
) -> Any:
    """Convert arbitrary logging values into JSON-safe values."""

    try:
        json.dumps(
            value,
            ensure_ascii=False,
        )
        return value
    except (
        TypeError,
        ValueError,
    ):
        return repr(value)


class JsonFormatter(logging.Formatter):
    """Single-line structured JSON formatter."""

    def __init__(
        self,
        *,
        environment: str = "dev",
        service: str | None = None,
        version: str | None = None,
    ) -> None:
        super().__init__()

        self.environment = environment
        self.service = service
        self.version = version

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        )

        trace_id = (
            trace_id_var.get()
            or _get_otel_trace_id()
        )

        entry: dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "environment": self.environment,
        }

        if self.service:
            entry["service"] = self.service

        if self.version:
            entry["version"] = self.version

        context = {
            "trace_id": trace_id,
            "request_id": request_id_var.get(),
            "org_id": org_id_var.get(),
            "user_id": user_id_var.get(),
        }

        for key, value in context.items():
            if value:
                entry[key] = value

        # ``extra={"foo": "bar"}``
        for key, value in record.__dict__.items():
            if (
                key in _RESERVED_LOG_RECORD_FIELDS
                or key.startswith("_")
            ):
                continue

            entry[key] = _json_safe(value)

        if record.exc_info:
            entry["exception"] = {
                "type": (
                    record.exc_info[0].__name__
                    if record.exc_info[0]
                    else "Exception"
                ),
                "message": str(
                    record.exc_info[1]
                ),
                "traceback": self.formatException(
                    record.exc_info
                ),
            }

        return json.dumps(
            entry,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )


# ---------------------------------------------------------------------------
# Text formatter
# ---------------------------------------------------------------------------


class TextFormatter(logging.Formatter):
    """Human-readable development formatter."""

    def __init__(
        self,
        *,
        environment: str = "dev",
    ) -> None:
        super().__init__(
            fmt=(
                "%(asctime)s | "
                "%(levelname)-8s | "
                "%(name)s:%(funcName)s:%(lineno)d | "
                "%(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        self.environment = environment

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        trace_id = (
            trace_id_var.get()
            or _get_otel_trace_id()
        )

        message = record.getMessage()

        if trace_id:
            message = (
                f"[trace={trace_id[:16]}] "
                f"{message}"
            )

        # Avoid mutating the shared LogRecord.
        original = record.msg
        original_args = record.args

        try:
            record.msg = message
            record.args = ()

            return super().format(
                record
            )

        finally:
            record.msg = original
            record.args = original_args


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


_configured = False


def configure_logging(
    *,
    level: str = "INFO",
    log_format: str = "json",
    environment: str = "dev",
    service: str | None = None,
    version: str | None = None,
    force: bool = False,
) -> None:
    """
    Configure application logging.

    Production:
        configure_logging(
            level="INFO",
            log_format="json",
            environment="production",
        )

    Development:
        configure_logging(
            level="DEBUG",
            log_format="text",
            environment="development",
        )
    """

    global _configured

    normalized_level = level.upper()

    if not hasattr(
        logging,
        normalized_level,
    ):
        raise ValueError(
            f"invalid log level: {level!r}"
        )

    if log_format not in {
        "json",
        "text",
    }:
        raise ValueError(
            "log_format must be 'json' or 'text'"
        )

    if _configured and not force:
        return

    root = logging.getLogger()

    if force:
        for handler in root.handlers[:]:
            root.removeHandler(
                handler
            )
            handler.close()

    handler = logging.StreamHandler(
        sys.stdout
    )

    handler.set_name(
        "platform-structured"
    )

    if log_format == "json":
        handler.setFormatter(
            JsonFormatter(
                environment=environment,
                service=service,
                version=version,
            )
        )
    else:
        handler.setFormatter(
            TextFormatter(
                environment=environment
            )
        )

    root.addHandler(
        handler
    )

    root.setLevel(
        normalized_level
    )

    # Keep application logs visible while avoiding duplicated/noisy
    # framework internals.
    for noisy_logger in (
        "httpcore",
        "httpx",
        "urllib3",
    ):
        logging.getLogger(
            noisy_logger
        ).setLevel(logging.WARNING)

    _configured = True

    logging.getLogger(
        __name__
    ).debug(
        "logging configured",
        extra={
            "log_format": log_format,
            "log_level": normalized_level,
            "environment": environment,
        },
    )


def get_logger(
    name: str,
) -> logging.Logger:
    """Return a named structured logger."""

    return logging.getLogger(
        name
    )


__all__ = [
    "JsonFormatter",
    "TextFormatter",
    "clear_trace_context",
    "configure_logging",
    "get_logger",
    "get_trace_id",
    "org_id_var",
    "request_id_var",
    "set_trace_context",
    "trace_context",
    "trace_id_var",
    "user_id_var",
]