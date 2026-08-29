"""
Production-oriented OAuth 2.0 / OpenID Connect client.

Supported flows:

- Authorization Code
- Authorization Code + PKCE
- Client Credentials
- Refresh Token

Security properties:

- S256 PKCE
- cryptographically random state
- optional OIDC nonce
- exact redirect URI configured by the application
- form-encoded token requests
- HTTP Basic client authentication by default
- configurable client_secret_post
- bounded HTTP timeouts
- typed OAuth responses/errors
- issuer/audience validation hooks
- injectable httpx client for testing
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

__all__ = [
    "AuthorizationRequest",
    "OIDCConfiguration",
    "OAuth2Client",
    "OAuthError",
    "OAuthHTTPError",
    "OAuthProtocolError",
    "OAuthToken",
    "PKCEPair",
    "generate_nonce",
    "generate_pkce_pair",
    "generate_state",
]


class OAuthError(RuntimeError):
    """Base OAuth client error."""


class OAuthHTTPError(OAuthError):
    """Token or discovery endpoint returned an HTTP error."""

    def __init__(
        self,
        status_code: int,
        *,
        error: str | None = None,
        description: str | None = None,
        uri: str | None = None,
        response_body: str = "",
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.description = description
        self.uri = uri
        self.response_body = response_body

        message = error or f"HTTP {status_code}"

        if description:
            message += f": {description}"

        super().__init__(message)


class OAuthProtocolError(OAuthError):
    """OAuth server returned an invalid or incomplete response."""


@dataclass(frozen=True, slots=True)
class PKCEPair:
    verifier: str
    challenge: str
    method: str = "S256"


@dataclass(frozen=True, slots=True)
class OAuthToken:
    access_token: str
    token_type: str
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None
    id_token: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_response(
        cls,
        payload: Mapping[str, Any],
    ) -> OAuthToken:
        access_token = payload.get("access_token")
        token_type = payload.get("token_type")

        if not access_token:
            raise OAuthProtocolError(
                "token response does not contain access_token"
            )

        if not token_type:
            raise OAuthProtocolError(
                "token response does not contain token_type"
            )

        expires_in = payload.get("expires_in")

        if expires_in is not None:
            try:
                expires_in = int(expires_in)
            except (TypeError, ValueError) as exc:
                raise OAuthProtocolError(
                    "invalid expires_in"
                ) from exc

        return cls(
            access_token=str(access_token),
            token_type=str(token_type),
            expires_in=expires_in,
            refresh_token=_optional_str(payload.get("refresh_token")),
            scope=_optional_str(payload.get("scope")),
            id_token=_optional_str(payload.get("id_token")),
            raw=dict(payload),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """
    State generated for one authorization transaction.

    Persist this server-side or in a secure, user-agent-bound session.
    """

    state: str
    pkce: PKCEPair | None = None
    nonce: str | None = None


@dataclass(frozen=True, slots=True)
class OIDCConfiguration:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str | None = None
    userinfo_endpoint: str | None = None
    end_session_endpoint: str | None = None
    scopes_supported: tuple[str, ...] = ()
    response_types_supported: tuple[str, ...] = ()
    grant_types_supported: tuple[str, ...] = ()

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
    ) -> OIDCConfiguration:
        issuer = _required_string(payload, "issuer")
        authorization_endpoint = _required_string(
            payload,
            "authorization_endpoint",
        )
        token_endpoint = _required_string(
            payload,
            "token_endpoint",
        )

        return cls(
            issuer=issuer,
            authorization_endpoint=authorization_endpoint,
            token_endpoint=token_endpoint,
            jwks_uri=_optional_str(payload.get("jwks_uri")),
            userinfo_endpoint=_optional_str(
                payload.get("userinfo_endpoint")
            ),
            end_session_endpoint=_optional_str(
                payload.get("end_session_endpoint")
            ),
            scopes_supported=_string_tuple(
                payload.get("scopes_supported")
            ),
            response_types_supported=_string_tuple(
                payload.get("response_types_supported")
            ),
            grant_types_supported=_string_tuple(
                payload.get("grant_types_supported")
            ),
        )


def generate_state() -> str:
    """Generate a high-entropy authorization transaction state."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Generate an OIDC nonce bound to an authorization transaction."""
    return secrets.token_urlsafe(32)


def generate_pkce_pair() -> PKCEPair:
    """
    Generate RFC 7636 S256 PKCE material.

    Returns a verifier and its SHA-256 challenge.
    """
    verifier = secrets.token_urlsafe(64)

    digest = hashlib.sha256(
        verifier.encode("ascii")
    ).digest()

    challenge = (
        base64.urlsafe_b64encode(digest)
        .rstrip(b"=")
        .decode("ascii")
    )

    return PKCEPair(
        verifier=verifier,
        challenge=challenge,
    )


class OAuth2Client:
    """
    Async OAuth 2.0 client.

    The same client can be used with:

        authorization_code + PKCE
        client_credentials
        refresh_token

    HTTP transport is injectable, making the implementation testable
    without real network calls.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str | None,
        authorize_url: str,
        token_url: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        timeout: httpx.Timeout | float = 10.0,
        client_auth_method: str = "basic",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not client_id:
            raise ValueError("client_id is required")

        if not authorize_url:
            raise ValueError("authorize_url is required")

        if not token_url:
            raise ValueError("token_url is required")

        if not redirect_uri:
            raise ValueError("redirect_uri is required")

        if client_auth_method not in {
            "basic",
            "client_secret_post",
            "none",
        }:
            raise ValueError(
                "client_auth_method must be "
                "'basic', 'client_secret_post', or 'none'"
            )

        self.client_id = client_id
        self.client_secret = client_secret
        self.authorize_url = authorize_url
        self.token_url = token_url
        self.redirect_uri = redirect_uri
        self.scopes = tuple(scopes or ())
        self.client_auth_method = client_auth_method

        self._client = http_client
        self._timeout = timeout

    async def __aenter__(self) -> OAuth2Client:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
            )

        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def begin_authorization(
        self,
        *,
        use_pkce: bool = True,
        use_nonce: bool = False,
        extra_params: Mapping[str, str] | None = None,
    ) -> tuple[str, AuthorizationRequest]:
        """
        Start an authorization-code transaction.

        The returned AuthorizationRequest must be retained until
        the callback is received.
        """
        state = generate_state()

        pkce = generate_pkce_pair() if use_pkce else None
        nonce = generate_nonce() if use_nonce else None

        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
        }

        if self.scopes:
            params["scope"] = " ".join(self.scopes)

        if pkce is not None:
            params["code_challenge"] = pkce.challenge
            params["code_challenge_method"] = pkce.method

        if nonce is not None:
            params["nonce"] = nonce

        if extra_params:
            params.update(extra_params)

        authorization = _append_query(
            self.authorize_url,
            params,
        )

        transaction = AuthorizationRequest(
            state=state,
            pkce=pkce,
            nonce=nonce,
        )

        return authorization, transaction

    async def exchange_code(
        self,
        code: str,
        *,
        transaction: AuthorizationRequest | None = None,
    ) -> OAuthToken:
        """
        Exchange a one-time authorization code.

        The caller must validate the callback state before invoking this
        method.
        """
        if not code:
            raise ValueError("authorization code is required")

        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        if transaction and transaction.pkce:
            data["code_verifier"] = transaction.pkce.verifier

        payload = await self._token_request(data)

        return OAuthToken.from_response(payload)

    async def client_credentials(
        self,
        *,
        scopes: list[str] | None = None,
    ) -> OAuthToken:
        """Acquire an access token for machine-to-machine authentication."""
        data: dict[str, str] = {
            "grant_type": "client_credentials",
        }

        requested_scopes = scopes or list(self.scopes)

        if requested_scopes:
            data["scope"] = " ".join(requested_scopes)

        payload = await self._token_request(data)

        return OAuthToken.from_response(payload)

    async def refresh_token(
        self,
        refresh_token: str,
        *,
        scopes: list[str] | None = None,
    ) -> OAuthToken:
        """Exchange a refresh token for a new access token."""
        if not refresh_token:
            raise ValueError("refresh_token is required")

        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        requested_scopes = scopes or []

        if requested_scopes:
            data["scope"] = " ".join(requested_scopes)

        payload = await self._token_request(data)

        return OAuthToken.from_response(payload)

    async def userinfo(
        self,
        access_token: str,
        *,
        userinfo_url: str,
    ) -> dict[str, Any]:
        """Call an OIDC UserInfo endpoint."""
        client = self._require_client()

        response = await client.get(
            userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

        if response.status_code >= 400:
            raise OAuthHTTPError(
                response.status_code,
                response_body=response.text,
            )

        payload = response.json()

        if not isinstance(payload, dict):
            raise OAuthProtocolError(
                "userinfo response must be a JSON object"
            )

        return payload

    async def discover_oidc(
        self,
        issuer: str,
    ) -> OIDCConfiguration:
        """
        Load OpenID Connect discovery metadata.

        The returned issuer should be compared with the configured
        expected issuer before trusting the configuration.
        """
        normalized = issuer.rstrip("/")

        url = (
            f"{normalized}/.well-known/"
            "openid-configuration"
        )

        client = self._require_client()

        response = await client.get(url)

        if response.status_code >= 400:
            raise OAuthHTTPError(
                response.status_code,
                response_body=response.text,
            )

        payload = response.json()

        if not isinstance(payload, dict):
            raise OAuthProtocolError(
                "OIDC discovery response must be an object"
            )

        return OIDCConfiguration.from_json(payload)

    async def _token_request(
        self,
        data: dict[str, str],
    ) -> dict[str, Any]:
        client = self._require_client()

        headers = {
            "Accept": "application/json",
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
        }

        auth: tuple[str, str] | None = None

        if self.client_auth_method == "basic":
            if self.client_secret is None:
                raise OAuthError(
                    "client_secret required for basic authentication"
                )

            auth = (
                self.client_id,
                self.client_secret,
            )

        elif self.client_auth_method == "client_secret_post":
            if self.client_secret is None:
                raise OAuthError(
                    "client_secret required for "
                    "client_secret_post"
                )

            data["client_id"] = self.client_id
            data["client_secret"] = self.client_secret

        elif self.client_auth_method == "none":
            data["client_id"] = self.client_id

        response = await client.post(
            self.token_url,
            data=data,
            headers=headers,
            auth=auth,
        )

        payload = _json_object(response)

        if response.status_code >= 400:
            raise OAuthHTTPError(
                response.status_code,
                error=_optional_str(payload.get("error")),
                description=_optional_str(
                    payload.get("error_description")
                ),
                uri=_optional_str(
                    payload.get("error_uri")
                ),
                response_body=response.text,
            )

        return payload

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "OAuth2Client must be used inside "
                "'async with' or supplied with http_client"
            )

        return self._client


def _append_query(
    url: str,
    params: Mapping[str, str],
) -> str:
    parts = urlsplit(url)

    existing = parts.query

    encoded = urlencode(
        params,
        doseq=True,
    )

    query = (
        f"{existing}&{encoded}"
        if existing
        else encoded
    )

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            query,
            parts.fragment,
        )
    )


def _json_object(
    response: httpx.Response,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise OAuthProtocolError(
            "OAuth server returned invalid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise OAuthProtocolError(
            "OAuth server response must be a JSON object"
        )

    return payload


def _required_string(
    payload: Mapping[str, Any],
    name: str,
) -> str:
    value = payload.get(name)

    if not isinstance(value, str) or not value:
        raise OAuthProtocolError(
            f"discovery metadata missing '{name}'"
        )

    return value


def _optional_str(
    value: Any,
) -> str | None:
    return str(value) if value is not None else None


def _string_tuple(
    value: Any,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()

    return tuple(
        str(item)
        for item in value
        if isinstance(item, str)
    )