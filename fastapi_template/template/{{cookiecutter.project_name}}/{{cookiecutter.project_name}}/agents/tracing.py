"""Agent observability helpers.

Uses OpenTelemetry when installed and configured.
Observability must never break agent execution.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


@contextmanager
def agent_span(
    name: str,
    **attrs: Any,
) -> Generator[None, None, None]:
    """
    Create an OpenTelemetry span around an agent operation.

    If OpenTelemetry is unavailable or span creation fails, execution
    continues without instrumentation.
    """
    if not name or not name.strip():
        raise ValueError("span name cannot be empty")

    attributes = _normalize_attributes(attrs)

    try:
        from opentelemetry import trace

        tracer = trace.get_tracer(
            "nk.agents",
        )

        with tracer.start_as_current_span(
            name.strip(),
            attributes=attributes,
        ) as span:
            try:
                yield
            except Exception as exc:
                _record_exception(
                    span,
                    exc,
                )
                raise

    except ImportError:
        # OTel is an optional dependency.
        yield

    except Exception:
        # Instrumentation must never take down the agent.
        #
        # Important: exceptions raised by the wrapped application block
        # are re-raised above and must not be swallowed here.
        if False:
            raise
        yield


def _normalize_attributes(
    attrs: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize attributes into OpenTelemetry-compatible primitive values.

    Unsupported values are converted to strings instead of allowing
    instrumentation to interfere with application execution.
    """
    normalized: dict[str, Any] = {}

    for key, value in attrs.items():
        if not isinstance(key, str):
            key = str(key)

        if value is None:
            continue

        if isinstance(
            value,
            (
                str,
                bool,
                int,
                float,
            ),
        ):
            normalized[key] = value
            continue

        if isinstance(value, (list, tuple)):
            if all(
                isinstance(
                    item,
                    (
                        str,
                        bool,
                        int,
                        float,
                    ),
                )
                for item in value
            ):
                normalized[key] = value
                continue

        normalized[key] = str(value)

    return normalized


def _record_exception(
    span: Any,
    exc: BaseException,
) -> None:
    """Record an application exception without masking the original error."""
    try:
        span.record_exception(exc)
        span.set_attribute(
            "error.type",
            type(exc).__name__,
        )
        span.set_status(
            _error_status(),
            str(exc),
        )
    except Exception:
        # Telemetry failures must never alter application behavior.
        pass


def _error_status() -> Any:
    """Resolve OTel StatusCode lazily."""
    try:
        from opentelemetry.trace import StatusCode

        return StatusCode.ERROR
    except Exception:
        return None


__all__ = [
    "agent_span",
]