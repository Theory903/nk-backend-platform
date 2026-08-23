from fastapi import FastAPI
from httpx import AsyncClient
from starlette import status

from {{cookiecutter.project_name}}.core.errors import PROBLEM_CONTENT_TYPE, Problem

PROBLEM_TYPE_RFC = "https://datatracker.ietf.org/doc/html/rfc9457"


async def test_unknown_route_returns_problem_json(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """
    Unmatched routes answer with RFC 9457 problem details.
    """
    response = await client.get("/api/definitely-missing-route")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["status"] == status.HTTP_404_NOT_FOUND
    assert body["title"]
    assert body["instance"] == "/api/definitely-missing-route"


async def test_validation_error_returns_problem_json(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """
    Malformed payloads answer with a 422 problem document.
    """
    response = await client.post(
        fastapi_app.url_path_for("send_echo_message"),
        json={"wrong_field": "nope"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == PROBLEM_TYPE_RFC
    assert body["detail"]


async def test_problem_exception_maps_to_response(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """
    Raising Problem produces a typed problem response.
    """

    @fastapi_app.get("/problem-probe")
    async def probe() -> None:
        raise Problem(
            "Out of credit",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="balance exhausted",
        )

    response = await client.get("/problem-probe")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["title"] == "Out of credit"
    assert body["detail"] == "balance exhausted"
    assert body["instance"] == "/problem-probe"
