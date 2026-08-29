"""RFC 9457 problem-details handler coverage."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from starlette import status
from starlette.requests import ClientDisconnect

from {{cookiecutter.project_name}}.core.errors import (
    PROBLEM_CONTENT_TYPE,
    PROBLEM_TYPE_RFC,
    Problem,
    problem_response,
)


async def test_unknown_route_returns_problem_json(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """Unmatched routes answer with RFC 9457 problem details."""
    response = await client.get("/api/definitely-missing-route")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["type"] == PROBLEM_TYPE_RFC
    assert body["status"] == status.HTTP_404_NOT_FOUND
    assert body["title"] == "Not Found"
    assert body["instance"] == "/api/definitely-missing-route"


async def test_validation_error_returns_structured_errors(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """Malformed payloads answer with a 422 problem document and safe errors."""
    response = await client.post(
        fastapi_app.url_path_for("send_echo_message"),
        json={"wrong_field": "nope"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == PROBLEM_TYPE_RFC
    assert body["title"] == "Validation Failed"
    assert body["detail"]
    assert "errors" in body
    assert isinstance(body["errors"], list)
    assert body["errors"]
    for err in body["errors"]:
        assert "loc" in err
        assert "msg" in err
        assert "type" in err
        assert "input" not in err
        assert "ctx" not in err


async def test_problem_exception_maps_to_response(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """Raising Problem produces a typed problem response with extensions."""

    @fastapi_app.get("/problem-probe")
    async def probe() -> None:
        raise Problem(
            title="Out of credit",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="balance exhausted",
            type_uri="https://api.example.com/problems/out-of-credit",
            extensions={"code": "OUT_OF_CREDIT"},
        )

    response = await client.get("/problem-probe")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["type"] == "https://api.example.com/problems/out-of-credit"
    assert body["title"] == "Out of credit"
    assert body["detail"] == "balance exhausted"
    assert body["instance"] == "/problem-probe"
    assert body["code"] == "OUT_OF_CREDIT"


async def test_http_exception_dict_detail_moves_to_extensions(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """Structured HTTPException.detail stays out of the RFC detail string."""

    @fastapi_app.get("/http-dict-probe")
    async def probe() -> None:
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_INPUT", "field": "email"},
            headers={"X-Error-Code": "BAD_INPUT"},
        )

    response = await client.get("/http-dict-probe")

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert response.headers["x-error-code"] == "BAD_INPUT"
    body = response.json()
    assert body["title"] == "Bad Request"
    assert body["detail"] == "Bad Request"
    assert body["error"] == {"code": "BAD_INPUT", "field": "email"}
    assert "{" not in body["detail"]


async def test_unexpected_exception_hides_internals(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """Generic failures return a safe 500 problem document."""

    @fastapi_app.get("/boom-probe")
    async def boom() -> None:
        raise RuntimeError("secret database password leaked")

    response = await client.get("/boom-probe")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["title"] == "Internal Server Error"
    assert body["detail"] == "An unexpected error occurred."
    assert "secret" not in body["detail"].lower()
    assert "password" not in str(body).lower()


async def test_client_disconnect_is_not_mapped_to_500(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """ClientDisconnect must not become a problem+json 500."""

    @fastapi_app.get("/disconnect-probe")
    async def probe() -> None:
        raise ClientDisconnect()

    response = await client.get("/disconnect-probe")

    assert response.status_code == 499
    assert "application/problem+json" not in response.headers.get("content-type", "")


def test_problem_rejects_invalid_status_and_empty_title() -> None:
    with pytest.raises(ValueError, match="status_code"):
        Problem(title="Bad", status_code=200)

    with pytest.raises(ValueError, match="title"):
        Problem(title="   ", status_code=400)

    with pytest.raises(ValueError, match="reserved"):
        Problem(
            title="Conflict",
            status_code=409,
            extensions={"status": 999},
        )


def test_problem_strips_title_whitespace() -> None:
    problem = Problem(title="  Locked  ", status_code=423)
    assert problem.title == "Locked"


def test_problem_response_omits_null_optional_members() -> None:
    response = problem_response(status_code=404, title="Not Found")
    assert response.status_code == 404
    assert response.media_type == PROBLEM_CONTENT_TYPE
    assert response.body
    import json

    body = json.loads(response.body)
    assert body == {
        "type": PROBLEM_TYPE_RFC,
        "title": "Not Found",
        "status": 404,
    }
