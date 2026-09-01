"""Tests for identity.deps authentication / authorization dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from {{cookiecutter.project_name}}.core.errors import register_problem_handlers
from {{cookiecutter.project_name}}.core.security import create_token
from {{cookiecutter.project_name}}.identity import deps as auth_deps
from {{cookiecutter.project_name}}.identity.api_keys import ApiKeyStore
from {{cookiecutter.project_name}}.identity.deps import (
    Anonymous,
    CurrentUser,
    OptionalUser,
    RequirePermission,
    RequireRole,
    configure_auth_stores,
)
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.identity.session import SessionStore


SECRET = "unit-test-users-secret-32chars!!"


@pytest.fixture(autouse=True)
def _reset_auth_stores() -> None:
    auth_deps._api_key_store = None
    auth_deps._session_store = None
    auth_deps._csrf_protection = None
    auth_deps._access_token_store = None
    auth_deps._service_accounts = None
    auth_deps._account_active_checker = None
    yield
    auth_deps._api_key_store = None
    auth_deps._session_store = None
    auth_deps._csrf_protection = None
    auth_deps._access_token_store = None
    auth_deps._service_accounts = None
    auth_deps._account_active_checker = None


@pytest.fixture
def api_keys() -> ApiKeyStore:
    return ApiKeyStore()


@pytest.fixture
def sessions() -> SessionStore:
    return SessionStore()


@pytest.fixture
def app(api_keys: ApiKeyStore, sessions: SessionStore, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Minimal profile Settings may omit users_secret; deps reads via getattr.
    monkeypatch.setattr(
        auth_deps,
        "settings",
        type(
            "SettingsStub",
            (),
            {
                "users_secret": SECRET,
                "auth_token_ttl_seconds": 3600,
                "session_cookie_max_age_seconds": 86_400,
                "security_require_auth": True,
            },
        )(),
    )
    configure_auth_stores(api_keys=api_keys, sessions=sessions)

    application = FastAPI()
    register_problem_handlers(application)

    @application.get("/me")
    def me(principal: Principal = Depends(CurrentUser)) -> dict:
        return {
            "user_id": principal.user_id,
            "provider": principal.provider,
            "is_service": principal.is_service,
            "roles": sorted(principal.roles),
        }

    @application.get("/optional")
    def optional(principal: Principal = Depends(OptionalUser)) -> dict:
        return {
            "user_id": principal.user_id,
            "is_anonymous": principal.is_anonymous,
        }

    @application.get(
        "/admin",
        dependencies=[Depends(RequirePermission("admin.read"))],
    )
    def admin_route(principal: Principal = Depends(CurrentUser)) -> dict:
        return {"ok": True, "user_id": principal.user_id}

    @application.get("/role-admin")
    def role_admin(principal: Principal = Depends(RequireRole("admin"))) -> dict:
        return {"ok": True, "user_id": principal.user_id}

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.mark.anyio
async def test_stores_required_returns_500(client: AsyncClient) -> None:
    auth_deps._api_key_store = None
    auth_deps._session_store = None
    response = await client.get("/me", headers={"Authorization": "ApiKey nk_x_y"})
    assert response.status_code == 500
    body = response.json()
    assert "store" in body.get("detail", "").lower() or "configured" in body.get(
        "detail",
        "",
    ).lower()


@pytest.mark.anyio
async def test_bearer_invalid_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        "/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_bearer_valid(client: AsyncClient) -> None:
    token = create_token("user_abc", SECRET, ttl_s=300)
    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user_abc"
    assert data["provider"] == "token"
    assert data["is_service"] is False


@pytest.mark.anyio
async def test_api_key_principal_uses_svc_key_id(
    client: AsyncClient,
    api_keys: ApiKeyStore,
) -> None:
    raw, record = api_keys.create("ci-bot", owner_id="owner_1")
    response = await client.get("/me", headers={"Authorization": f"ApiKey {raw}"})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == f"svc:{record.key_id}"
    assert data["user_id"].startswith("svc:")
    assert data["is_service"] is True
    assert data["provider"] == "api_key"
    assert "ci-bot" not in data["user_id"]


@pytest.mark.anyio
async def test_apikey_scheme_case_insensitive(
    client: AsyncClient,
    api_keys: ApiKeyStore,
) -> None:
    raw, record = api_keys.create("bot")
    response = await client.get("/me", headers={"Authorization": f"APIKEY {raw}"})
    assert response.status_code == 200
    assert response.json()["user_id"] == f"svc:{record.key_id}"


@pytest.mark.anyio
async def test_malformed_authorization_returns_401(client: AsyncClient) -> None:
    response = await client.get("/me", headers={"Authorization": "Bearer"})
    assert response.status_code == 401

    response = await client.get("/me", headers={"Authorization": "Bearer a b"})
    assert response.status_code == 401

    response = await client.get("/me", headers={"Authorization": "Basic xyz"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_session_cookie_path(
    client: AsyncClient,
    sessions: SessionStore,
) -> None:
    sid = sessions.create("user_sess", data={"roles": ["viewer"]})
    response = await client.get("/me", cookies={"session": sid})
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user_sess"
    assert data["provider"] == "session"
    assert "viewer" in data["roles"]


@pytest.mark.anyio
async def test_x_session_id_header(
    client: AsyncClient,
    sessions: SessionStore,
) -> None:
    sid = sessions.create("user_hdr")
    response = await client.get("/me", headers={"X-Session-Id": sid})
    assert response.status_code == 200
    assert response.json()["user_id"] == "user_hdr"


@pytest.mark.anyio
async def test_optional_user_anonymous(client: AsyncClient) -> None:
    response = await client.get("/optional")
    assert response.status_code == 200
    data = response.json()
    assert data["is_anonymous"] is True
    assert data["user_id"] == ""
    assert Anonymous.is_anonymous is True


@pytest.mark.anyio
async def test_optional_user_invalid_creds_still_401(client: AsyncClient) -> None:
    response = await client.get(
        "/optional",
        headers={"Authorization": "Bearer bad-token"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_require_permission_403_without_perm(
    client: AsyncClient,
    sessions: SessionStore,
) -> None:
    sid = sessions.create("viewer_only", data={"roles": ["viewer"]})
    response = await client.get("/admin", cookies={"session": sid})
    assert response.status_code == 403
    assert "admin.read" in response.json().get("detail", "")


@pytest.mark.anyio
async def test_require_permission_allows_admin(
    client: AsyncClient,
    sessions: SessionStore,
) -> None:
    sid = sessions.create("boss", data={"roles": ["admin"]})
    response = await client.get("/admin", cookies={"session": sid})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_require_role_403(
    client: AsyncClient,
    sessions: SessionStore,
) -> None:
    sid = sessions.create("viewer_only", data={"roles": ["viewer"]})
    response = await client.get("/role-admin", cookies={"session": sid})
    assert response.status_code == 403


@pytest.mark.anyio
async def test_unauthenticated_current_user_401(client: AsyncClient) -> None:
    response = await client.get("/me")
    assert response.status_code == 401
