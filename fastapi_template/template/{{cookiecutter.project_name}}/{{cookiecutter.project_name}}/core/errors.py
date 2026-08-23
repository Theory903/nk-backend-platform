from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_RFC = "https://datatracker.ietf.org/doc/html/rfc9457"

_HTTP_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    410: "Gone",
    422: "Validation Failed",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


class Problem(Exception):
    """
    RFC 9457 problem raised anywhere inside request handling.
    """

    def __init__(
        self,
        title: str,
        status_code: int = 500,
        detail: str | None = None,
        instance: str | None = None,
        type_uri: str = PROBLEM_TYPE_RFC,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.title = title
        self.status_code = status_code
        self.detail = detail
        self.instance = instance
        self.type_uri = type_uri
        self.headers = headers
        super().__init__(detail or title)


def problem_response(
    status_code: int,
    title: str,
    detail: str | None = None,
    instance: str | None = None,
    type_uri: str = PROBLEM_TYPE_RFC,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response with only meaningful members."""
    content: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
    }
    if detail is not None:
        content["detail"] = detail
    if instance is not None:
        content["instance"] = instance
    return JSONResponse(
        content=content,
        status_code=status_code,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def register_problem_handlers(app: FastAPI) -> None:
    """
    Install RFC 9457 handlers for Problem, HTTP errors and validation.
    """

    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return problem_response(
            status_code=exc.status_code,
            title=_HTTP_TITLES.get(exc.status_code, "Request Failed"),
            detail=str(exc.detail),
            instance=request.url.path,
            headers=getattr(exc, "headers", None),
        )

    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        summary = "; ".join(
            "{}: {}".format(
                ".".join(str(part) for part in error.get("loc", [])[1:]),
                error.get("msg"),
            )
            for error in exc.errors()[:5]
        )
        return problem_response(
            status_code=422,
            title=_HTTP_TITLES[422],
            detail=summary,
            instance=request.url.path,
        )

    async def handle_problem(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            instance=exc.instance or request.url.path,
            type_uri=exc.type_uri,
            headers=exc.headers,
        )

    app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Problem, handle_problem)  # type: ignore[arg-type]
