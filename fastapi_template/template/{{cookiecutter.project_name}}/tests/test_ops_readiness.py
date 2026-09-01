from fastapi import FastAPI
from httpx import AsyncClient
import asyncio

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.web.api.monitoring.views import register_readiness_check


async def test_liveness_is_dependency_free(fastapi_app: FastAPI, client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"


async def test_readiness_reports_registered_failures(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    async def broken() -> None:
        raise RuntimeError("downstream unavailable")

    register_readiness_check("unit_probe_broken", broken)
    try:
        response = await client.get("/api/ready")
    finally:
        from {{cookiecutter.project_name}}.web.api.monitoring.views import _readiness_checks

        _readiness_checks.pop("unit_probe_broken", None)

    assert response.status_code == 503
    assert "unit_probe_broken" in response.json()["detail"]


async def test_readiness_times_out_slow_checks(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    """A stuck dependency cannot block the readiness endpoint indefinitely."""
    async def slow() -> None:
        await asyncio.sleep(1)

    fastapi_app.state.readiness_timeout_s = 0.01
    register_readiness_check("unit_probe_slow", slow)
    try:
        response = await client.get("/api/ready")
    finally:
        from {{cookiecutter.project_name}}.web.api.monitoring.views import _readiness_checks

        _readiness_checks.pop("unit_probe_slow", None)

    assert response.status_code == 503
    assert "unit_probe_slow" in response.json()["detail"]


async def test_problem_exception_maps_to_response(
    fastapi_app: FastAPI,
    client: AsyncClient,
) -> None:
    @fastapi_app.get("/problem-probe")
    async def probe() -> None:
        raise Problem(
            title="Out of credit",
            status_code=403,
            detail="balance exhausted",
        )

    response = await client.get("/problem-probe")

    assert response.status_code == 403
    assert response.json()["title"] == "Out of credit"
