"""RFC 9457 problem-details error handling for FastAPI."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect
from starlette.websockets import WebSocketDisconnect

from .logging import redact_text

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_RFC = "https://datatracker.ietf.org/doc/html/rfc9457"

_RESERVED_PROBLEM_MEMBERS = frozenset(
    {"type", "title", "status", "detail", "instance"}
)
_SENSITIVE_PROBLEM_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
)
_REDACTED = "[REDACTED]"

_HTTP_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    412: "Precondition Failed",
    413: "Content Too Large",
    415: "Unsupported Media Type",
    422: "Validation Failed",
    423: "Locked",
    424: "Failed Dependency",
    425: "Too Early",
    428: "Precondition Required",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def _validate_extensions(extensions: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy extensions, rejecting collisions with reserved RFC members."""
    if not extensions:
        return {}

    cleaned: dict[str, Any] = {}
    for key, value in extensions.items():
        if key in _RESERVED_PROBLEM_MEMBERS:
            raise ValueError(
                f"extension member conflicts with reserved field: {key}"
            )
        cleaned[key] = value
    return cleaned


def _safe_problem_value(value: Any, *, key: str | None = None) -> Any:
    """Redact secrets from problem details and extension values."""
    if key is not None:
        normalized = key.lower().replace("-", "_")
        if any(part in normalized for part in _SENSITIVE_PROBLEM_KEY_PARTS):
            return _REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(child_key): _safe_problem_value(
                child,
                key=str(child_key),
            )
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_problem_value(child) for child in value]
    return value


class Problem(Exception):
    """
    RFC 9457 application error.

    Raise this from application/domain code. The FastAPI handler converts
    it into a standards-compliant problem+json response.
    """

    def __init__(
        self,
        *,
        title: str,
        status_code: int,
        detail: str | None = None,
        type_uri: str = PROBLEM_TYPE_RFC,
        instance: str | None = None,
        headers: Mapping[str, str] | None = None,
        extensions: Mapping[str, Any] | None = None,
    ) -> None:
        if not 400 <= status_code <= 599:
            raise ValueError(
                "problem status_code must be between 400 and 599"
            )

        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("problem title must not be empty")

        self.title = normalized_title
        self.status_code = status_code
        self.detail = detail
        self.type_uri = type_uri
        self.instance = instance
        self.headers = dict(headers or {})
        self.extensions = _validate_extensions(extensions)

        super().__init__(detail or normalized_title)


def problem_response(
    *,
    status_code: int,
    title: str,
    detail: str | None = None,
    type_uri: str = PROBLEM_TYPE_RFC,
    instance: str | None = None,
    headers: Mapping[str, str] | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> JSONResponse:
    """Create an RFC 9457 problem-details response."""

    content: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
    }

    if detail is not None:
        content["detail"] = _safe_problem_value(detail)

    if instance is not None:
        content["instance"] = instance

    content.update(
        _safe_problem_value(_validate_extensions(extensions))
    )

    return JSONResponse(
        content=content,
        status_code=status_code,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=dict(headers or {}),
    )


def _http_title(status_code: int) -> str:
    return _HTTP_TITLES.get(status_code, "Request Failed")


def _correlation_headers(request: Request) -> dict[str, str]:
    """Return safe identifiers that let operators find the failed request."""
    headers: dict[str, str] = {}
    request_id = getattr(request.state, "request_id", None)
    trace_id = getattr(request.state, "trace_id", None)
    if isinstance(request_id, str) and request_id:
        headers["X-Request-ID"] = request_id
    if isinstance(trace_id, str) and trace_id:
        headers["X-Trace-ID"] = trace_id
    return headers


def _capture_unexpected(exc: Exception) -> None:
    """Report an unexpected error to Sentry when the optional SDK is active."""
    sentry_sdk = sys.modules.get("sentry_sdk")
    if sentry_sdk is None:
        return
    try:
        sentry_sdk.capture_exception(exc)
    except Exception:
        logger.exception("failed to report exception to Sentry")


def _normalize_http_detail(
    status_code: int,
    raw: Any,
) -> tuple[str | None, dict[str, Any]]:
    """
    Map FastAPI/Starlette HTTPException.detail into RFC members.

    RFC 9457 ``detail`` is a string. Structured payloads move into extensions.
    """
    if raw is None:
        return None, {}
    if isinstance(raw, str):
        return raw, {}
    if isinstance(raw, Mapping):
        return _http_title(status_code), {"error": dict(raw)}
    if isinstance(raw, list):
        return _http_title(status_code), {"errors": list(raw)}
    return str(raw), {}


def _format_validation_errors(
    exc: RequestValidationError,
) -> list[dict[str, Any]]:
    """
    Convert FastAPI validation errors into safe structured extensions.

    Only exposes location/type/message. The raw input value is deliberately
    excluded because it may contain credentials or personal data.
    """
    errors: list[dict[str, Any]] = []

    for error in exc.errors():
        location = list(error.get("loc", ()))

        if location and location[0] in {
            "body",
            "query",
            "path",
            "header",
            "cookie",
        }:
            location = location[1:]

        errors.append(
            {
                "loc": location,
                "msg": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "validation_error")),
            }
        )

    return errors


def register_problem_handlers(app: FastAPI) -> None:
    """
    Register the platform-wide exception handlers.

    Starlette dispatches by exception class MRO (not registration order).
    Handlers cover:
        Problem
        RequestValidationError
        Starlette HTTPException (also FastAPI HTTPException)
        unexpected Exception (excluding client/websocket disconnects)
    """

    async def handle_problem(
        request: Request,
        exc: Problem,
    ) -> JSONResponse:
        headers = _correlation_headers(request)
        headers.update(exc.headers)
        return problem_response(
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            type_uri=exc.type_uri,
            instance=exc.instance or str(request.url.path),
            headers=headers,
            extensions=exc.extensions,
        )

    async def handle_validation(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return problem_response(
            status_code=422,
            title="Validation Failed",
            detail="One or more request fields failed validation.",
            instance=str(request.url.path),
            headers=_correlation_headers(request),
            extensions={"errors": _format_validation_errors(exc)},
        )

    async def handle_http(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        detail, extensions = _normalize_http_detail(
            exc.status_code,
            exc.detail,
        )
        headers = _correlation_headers(request)
        if exc.headers:
            headers.update(exc.headers)
        return problem_response(
            status_code=exc.status_code,
            title=_http_title(exc.status_code),
            detail=detail,
            instance=str(request.url.path),
            headers=headers,
            extensions=extensions or None,
        )

    async def handle_unexpected(
        request: Request,
        exc: Exception,
    ) -> Response:
        # Disconnects are normal control flow — never map them to problem+json 500.
        if isinstance(exc, ClientDisconnect):
            return Response(status_code=499)
        if isinstance(exc, WebSocketDisconnect):
            # ServerErrorMiddleware only wraps HTTP; re-raise for the WS stack.
            raise exc

        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        _capture_unexpected(exc)
        return problem_response(
            status_code=500,
            title="Internal Server Error",
            detail="An unexpected error occurred.",
            instance=str(request.url.path),
            headers=_correlation_headers(request),
        )

    app.add_exception_handler(Problem, handle_problem)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http)
    app.add_exception_handler(Exception, handle_unexpected)


__all__ = [
    "PROBLEM_CONTENT_TYPE",
    "PROBLEM_TYPE_RFC",
    "Problem",
    "problem_response",
    "register_problem_handlers",
]
