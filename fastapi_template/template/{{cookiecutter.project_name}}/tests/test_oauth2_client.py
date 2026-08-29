"""Tests for production OAuth2Client: PKCE, form token posts, discovery."""

from __future__ import annotations

import base64
import hashlib
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from {{cookiecutter.project_name}}.identity.providers.oauth2 import (
    OAuth2Client,
    OAuthHTTPError,
    OAuthProtocolError,
    generate_pkce_pair,
)


TOKEN_PAYLOAD = {
    "access_token": "at-1",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "rt-1",
    "scope": "openid profile",
}


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _make_client(
    handler: Any,
    *,
    client_auth_method: str = "basic",
    client_secret: str | None = "secret",
    scopes: list[str] | None = None,
) -> OAuth2Client:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return OAuth2Client(
        client_id="cid",
        client_secret=client_secret,
        authorize_url="https://idp.example.com/authorize",
        token_url="https://idp.example.com/token",
        redirect_uri="https://app.example.com/callback",
        scopes=scopes or ["openid", "profile"],
        client_auth_method=client_auth_method,
        http_client=http,
    )


@pytest.mark.anyio
async def test_begin_authorization_includes_state_and_pkce() -> None:
    client = _make_client(lambda r: httpx.Response(500))
    url, txn = client.begin_authorization(use_pkce=True, use_nonce=True)

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert qs["response_type"] == ["code"]
    assert qs["client_id"] == ["cid"]
    assert qs["redirect_uri"] == ["https://app.example.com/callback"]
    assert qs["state"] == [txn.state]
    assert txn.pkce is not None
    assert qs["code_challenge"] == [txn.pkce.challenge]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["nonce"] == [txn.nonce]
    assert "openid" in qs["scope"][0]
    await client._client.aclose()  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_exchange_code_sends_form_body_and_code_verifier() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("content-type", "")
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.content.decode()
        # Must be form-encoded, not JSON
        assert "application/x-www-form-urlencoded" in captured["content_type"]
        assert not captured["body"].startswith("{")
        return httpx.Response(200, json=TOKEN_PAYLOAD)

    client = _make_client(handler)
    _, txn = client.begin_authorization(use_pkce=True)
    token = await client.exchange_code("auth-code-1", transaction=txn)

    form = parse_qs(captured["body"])
    assert captured["url"] == "https://idp.example.com/token"
    assert form["grant_type"] == ["authorization_code"]
    assert form["code"] == ["auth-code-1"]
    assert form["redirect_uri"] == ["https://app.example.com/callback"]
    assert form["code_verifier"] == [txn.pkce.verifier]  # type: ignore[union-attr]
    assert captured["authorization"] is not None  # HTTP Basic
    assert "client_secret" not in form
    assert token.access_token == "at-1"
    assert token.refresh_token == "rt-1"
    await client._client.aclose()  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_client_credentials_form_post() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={
                "access_token": "m2m",
                "token_type": "Bearer",
                "expires_in": "120",
            },
        )

    client = _make_client(handler, scopes=["api.read"])
    token = await client.client_credentials()

    assert "application/x-www-form-urlencoded" in captured["content_type"]
    form = parse_qs(captured["body"])
    assert form["grant_type"] == ["client_credentials"]
    assert form["scope"] == ["api.read"]
    assert token.access_token == "m2m"
    assert token.expires_in == 120
    await client._client.aclose()  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_refresh_token_form_post() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "access_token": "at-2",
                "token_type": "Bearer",
                "refresh_token": "rt-2",
            },
        )

    client = _make_client(handler, client_auth_method="client_secret_post")
    token = await client.refresh_token("rt-1", scopes=["openid"])

    form = parse_qs(captured["body"])
    assert form["grant_type"] == ["refresh_token"]
    assert form["refresh_token"] == ["rt-1"]
    assert form["scope"] == ["openid"]
    assert form["client_id"] == ["cid"]
    assert form["client_secret"] == ["secret"]
    assert token.access_token == "at-2"
    await client._client.aclose()  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_oauth_http_error_parses_error_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
                "error_description": "code expired",
                "error_uri": "https://idp.example.com/docs#error",
            },
        )

    client = _make_client(handler, client_auth_method="none", client_secret=None)
    with pytest.raises(OAuthHTTPError) as exc_info:
        await client.exchange_code("bad")

    err = exc_info.value
    assert err.status_code == 400
    assert err.error == "invalid_grant"
    assert err.description == "code expired"
    assert err.uri == "https://idp.example.com/docs#error"
    assert "invalid_grant" in str(err)
    await client._client.aclose()  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_discover_oidc() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/.well-known/openid-configuration")
        return httpx.Response(
            200,
            json={
                "issuer": "https://idp.example.com",
                "authorization_endpoint": "https://idp.example.com/authorize",
                "token_endpoint": "https://idp.example.com/token",
                "jwks_uri": "https://idp.example.com/jwks",
                "userinfo_endpoint": "https://idp.example.com/userinfo",
                "scopes_supported": ["openid", "profile"],
            },
        )

    client = _make_client(handler)
    config = await client.discover_oidc("https://idp.example.com/")

    assert config.issuer == "https://idp.example.com"
    assert config.token_endpoint == "https://idp.example.com/token"
    assert config.jwks_uri == "https://idp.example.com/jwks"
    assert config.scopes_supported == ("openid", "profile")
    await client._client.aclose()  # type: ignore[union-attr]


def test_pkce_challenge_shape_s256() -> None:
    pair = generate_pkce_pair()
    assert pair.method == "S256"
    assert pair.challenge == _pkce_challenge(pair.verifier)
    # URL-safe base64 without padding
    assert "=" not in pair.challenge
    assert "+" not in pair.challenge
    assert "/" not in pair.challenge
    assert len(pair.verifier) >= 43


@pytest.mark.anyio
async def test_token_response_missing_access_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})

    client = _make_client(handler)
    with pytest.raises(OAuthProtocolError, match="access_token"):
        await client.client_credentials()
    await client._client.aclose()  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_context_manager_owns_http_client() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content.decode())
        return httpx.Response(200, json=TOKEN_PAYLOAD)

    transport = httpx.MockTransport(handler)
    # Inject transport via subclassing AsyncClient created by __aenter__
    async with OAuth2Client(
        client_id="cid",
        client_secret="secret",
        authorize_url="https://idp.example.com/authorize",
        token_url="https://idp.example.com/token",
        redirect_uri="https://app.example.com/callback",
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        token = await client.client_credentials()
        assert token.access_token == "at-1"

    assert seen
    form = parse_qs(seen[0])
    assert form["grant_type"] == ["client_credentials"]
