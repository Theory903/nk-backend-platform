"""
OpenID Connect provider.

Responsibilities:

- OIDC discovery
- JWKS retrieval and caching
- ID-token signature validation (PyJWT + JWKS; not decode-only)
- issuer validation
- audience validation
- authorized-party validation
- nonce validation
- temporal claim validation
- UserInfo retrieval

Note:
    ``oauth2.OIDCConfiguration`` is a separate discovery DTO used by
    ``OAuth2Client.discover_oidc``. Prefer this module's
    ``OIDCConfiguration`` + ``OidcProvider`` when validating ID tokens.
    Import with aliases if both are needed in one module.

Requires:

    pip install httpx "PyJWT[crypto]" cryptography
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import InvalidTokenError
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

__all__ = [
    "IDToken",
    "IDTokenValidationError",
    "OIDCConfiguration",
    "OIDCDiscoveryError",
    "OIDCError",
    "OIDCKeyError",
    "OidcProvider",
]


class OIDCError(RuntimeError):
    """Base OIDC error."""


class OIDCDiscoveryError(OIDCError):
    """Provider discovery failed."""


class OIDCKeyError(OIDCError):
    """Provider signing keys could not be resolved."""


class IDTokenValidationError(OIDCError):
    """ID token failed validation."""


@dataclass(frozen=True, slots=True)
class OIDCConfiguration:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None = None
    end_session_endpoint: str | None = None

    scopes_supported: tuple[str, ...] = ()
    response_types_supported: tuple[str, ...] = ()
    grant_types_supported: tuple[str, ...] = ()
    id_token_signing_alg_values_supported: tuple[str, ...] = ()

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
    ) -> OIDCConfiguration:
        return cls(
            issuer=_required(payload, "issuer"),
            authorization_endpoint=_required(
                payload,
                "authorization_endpoint",
            ),
            token_endpoint=_required(
                payload,
                "token_endpoint",
            ),
            jwks_uri=_required(
                payload,
                "jwks_uri",
            ),
            userinfo_endpoint=_optional(
                payload.get("userinfo_endpoint"),
            ),
            end_session_endpoint=_optional(
                payload.get("end_session_endpoint"),
            ),
            scopes_supported=_string_tuple(
                payload.get("scopes_supported"),
            ),
            response_types_supported=_string_tuple(
                payload.get("response_types_supported"),
            ),
            grant_types_supported=_string_tuple(
                payload.get("grant_types_supported"),
            ),
            id_token_signing_alg_values_supported=_string_tuple(
                payload.get(
                    "id_token_signing_alg_values_supported",
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class IDToken:
    """
    Validated OpenID Connect ID Token.

    Claims remain available through `claims`.
    """

    issuer: str
    subject: str
    audience: tuple[str, ...]
    expiration: int
    issued_at: int
    claims: Mapping[str, Any]

    @property
    def email(self) -> str | None:
        return _optional(self.claims.get("email"))

    @property
    def email_verified(self) -> bool | None:
        value = self.claims.get("email_verified")

        if value is None:
            return None

        return bool(value)

    @property
    def name(self) -> str | None:
        return _optional(self.claims.get("name"))

    @property
    def nonce(self) -> str | None:
        return _optional(self.claims.get("nonce"))


class OidcProvider:
    """
    OpenID Connect provider client.

    Example:

        provider = OidcProvider(
            issuer_url="https://accounts.example.com",
            client_id="my-client",
        )

        token = await provider.validate_id_token(
            id_token,
            nonce=transaction.nonce,
        )
    """

    DEFAULT_ALGORITHMS = (
        "RS256",
        "RS384",
        "RS512",
        "ES256",
        "ES384",
        "ES512",
    )

    def __init__(
        self,
        issuer_url: str,
        *,
        client_id: str,
        allowed_algorithms: tuple[str, ...] | None = None,
        clock_skew_s: int = 60,
        discovery_ttl_s: int = 3600,
        jwks_ttl_s: int = 3600,
        timeout: httpx.Timeout | float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        issuer = issuer_url.rstrip("/")

        if not issuer:
            raise ValueError("issuer_url is required")

        if not client_id:
            raise ValueError("client_id is required")

        if clock_skew_s < 0:
            raise ValueError(
                "clock_skew_s must not be negative",
            )

        self.issuer_url = issuer
        self.client_id = client_id
        self.clock_skew_s = clock_skew_s

        self.discovery_ttl_s = discovery_ttl_s
        self.jwks_ttl_s = jwks_ttl_s

        self.allowed_algorithms = (
            allowed_algorithms
            or self.DEFAULT_ALGORITHMS
        )

        self._client = http_client
        self._timeout = timeout

        self._config: OIDCConfiguration | None = None
        self._config_expires_at = 0.0

        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

        self._discovery_lock = asyncio.Lock()
        self._jwks_lock = asyncio.Lock()

    async def __aenter__(self) -> OidcProvider:
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

    async def discover(
        self,
        *,
        force_refresh: bool = False,
    ) -> OIDCConfiguration:
        """Load and cache the provider discovery document."""
        now = time.monotonic()

        if (
            not force_refresh
            and self._config is not None
            and now < self._config_expires_at
        ):
            return self._config

        async with self._discovery_lock:
            now = time.monotonic()

            if (
                not force_refresh
                and self._config is not None
                and now < self._config_expires_at
            ):
                return self._config

            client = self._require_client()

            url = (
                f"{self.issuer_url}"
                "/.well-known/openid-configuration"
            )

            try:
                response = await client.get(url)

                response.raise_for_status()

                payload = response.json()

                if not isinstance(payload, dict):
                    raise OIDCDiscoveryError(
                        "discovery response is not an object",
                    )

                config = OIDCConfiguration.from_json(payload)

            except (
                httpx.HTTPError,
                ValueError,
                OIDCError,
            ) as exc:
                raise OIDCDiscoveryError(
                    f"OIDC discovery failed: {exc}",
                ) from exc

            # Discovery issuer must agree with the
            # configured issuer.
            if config.issuer != self.issuer_url:
                raise OIDCDiscoveryError(
                    "discovered issuer does not match "
                    "configured issuer",
                )

            self._config = config
            self._config_expires_at = (
                now + self.discovery_ttl_s
            )

            return config

    async def get_jwks(
        self,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Load and cache provider signing keys."""
        now = time.monotonic()

        if (
            not force_refresh
            and self._jwks is not None
            and now < self._jwks_expires_at
        ):
            return self._jwks

        async with self._jwks_lock:
            now = time.monotonic()

            if (
                not force_refresh
                and self._jwks is not None
                and now < self._jwks_expires_at
            ):
                return self._jwks

            config = await self.discover()

            client = self._require_client()

            try:
                response = await client.get(
                    config.jwks_uri,
                )

                response.raise_for_status()

                payload = response.json()

                if not isinstance(payload, dict):
                    raise OIDCKeyError(
                        "JWKS response is not an object",
                    )

            except (
                httpx.HTTPError,
                ValueError,
                OIDCError,
            ) as exc:
                raise OIDCKeyError(
                    f"JWKS retrieval failed: {exc}",
                ) from exc

            keys = payload.get("keys")

            if not isinstance(keys, list):
                raise OIDCKeyError(
                    "JWKS response does not contain keys",
                )

            self._jwks = payload
            self._jwks_expires_at = (
                now + self.jwks_ttl_s
            )

            return payload

    async def validate_id_token(
        self,
        id_token: str,
        *,
        nonce: str | None = None,
        max_age_s: int | None = None,
    ) -> IDToken:
        """
        Cryptographically and semantically validate an ID token.

        Validates:

        - JWT structure
        - signing algorithm
        - signing key
        - signature
        - issuer
        - audience
        - expiration
        - issued-at
        - optional nonce
        - optional max authentication age
        """
        if not id_token:
            raise IDTokenValidationError(
                "empty ID token",
            )

        try:
            header = jwt.get_unverified_header(
                id_token,
            )

            algorithm = header.get("alg")
            key_id = header.get("kid")

            if algorithm not in self.allowed_algorithms:
                raise IDTokenValidationError(
                    f"unsupported signing algorithm: "
                    f"{algorithm!r}",
                )

            if not key_id:
                raise IDTokenValidationError(
                    "ID token is missing kid",
                )

            config = await self.discover()

            jwks = await self.get_jwks()

            key = self._find_key(
                jwks,
                key_id,
            )

            # Key rotation race:
            # refresh JWKS once when kid is unknown.
            if key is None:
                jwks = await self.get_jwks(
                    force_refresh=True,
                )

                key = self._find_key(
                    jwks,
                    key_id,
                )

            if key is None:
                raise OIDCKeyError(
                    f"signing key {key_id!r} not found",
                )

            signing_key = self._build_key(
                key,
                algorithm,
            )

            claims = jwt.decode(
                id_token,
                signing_key,
                algorithms=[
                    algorithm,
                ],
                issuer=config.issuer,
                audience=self.client_id,
                leeway=self.clock_skew_s,
                options={
                    "require": [
                        "iss",
                        "sub",
                        "aud",
                        "exp",
                        "iat",
                    ],
                },
            )

            if not isinstance(claims, dict):
                raise IDTokenValidationError(
                    "ID token claims are not an object",
                )

            self._validate_claims(
                claims,
                nonce=nonce,
                max_age_s=max_age_s,
            )

            audience = _audience_tuple(
                claims.get("aud"),
            )

            return IDToken(
                issuer=str(claims["iss"]),
                subject=str(claims["sub"]),
                audience=audience,
                expiration=int(claims["exp"]),
                issued_at=int(claims["iat"]),
                claims=claims,
            )

        except IDTokenValidationError:
            raise

        except OIDCError:
            raise

        except InvalidTokenError as exc:
            raise IDTokenValidationError(
                f"invalid ID token: {exc}",
            ) from exc

        except Exception as exc:
            raise IDTokenValidationError(
                f"ID token validation failed: {exc}",
            ) from exc

    async def get_userinfo(
        self,
        access_token: str,
    ) -> dict[str, Any]:
        """Retrieve OIDC UserInfo claims."""
        if not access_token:
            raise ValueError(
                "access_token is required",
            )

        config = await self.discover()

        if not config.userinfo_endpoint:
            raise OIDCError(
                "provider does not expose UserInfo endpoint",
            )

        client = self._require_client()

        try:
            response = await client.get(
                config.userinfo_endpoint,
                headers={
                    "Authorization": (
                        f"Bearer {access_token}"
                    ),
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()

            payload = response.json()

        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:
            raise OIDCError(
                f"UserInfo request failed: {exc}",
            ) from exc

        if not isinstance(payload, dict):
            raise OIDCError(
                "UserInfo response is not an object",
            )

        return payload

    @staticmethod
    def _find_key(
        jwks: Mapping[str, Any],
        kid: str,
    ) -> Mapping[str, Any] | None:
        for key in jwks.get("keys", []):
            if (
                isinstance(key, dict)
                and key.get("kid") == kid
            ):
                return key

        return None

    @staticmethod
    def _build_key(
        jwk: Mapping[str, Any],
        algorithm: str,
    ) -> Any:
        key_type = jwk.get("kty")

        if algorithm.startswith("RS"):
            if key_type != "RSA":
                raise OIDCKeyError(
                    "RSA algorithm requires RSA JWK",
                )

            return RSAAlgorithm.from_jwk(
                _json_dumps(jwk),
            )

        if algorithm.startswith("ES"):
            if key_type != "EC":
                raise OIDCKeyError(
                    "EC algorithm requires EC JWK",
                )

            return ECAlgorithm.from_jwk(
                _json_dumps(jwk),
            )

        raise OIDCKeyError(
            f"unsupported algorithm: {algorithm}",
        )

    def _validate_claims(
        self,
        claims: Mapping[str, Any],
        *,
        nonce: str | None,
        max_age_s: int | None,
    ) -> None:
        subject = claims.get("sub")

        if not isinstance(subject, str) or not subject:
            raise IDTokenValidationError(
                "ID token has invalid sub",
            )

        issued_at = claims.get("iat")

        if not isinstance(issued_at, (int, float)):
            raise IDTokenValidationError(
                "ID token has invalid iat",
            )

        now = time.time()

        # Reject tokens issued too far in the future.
        if issued_at > now + self.clock_skew_s:
            raise IDTokenValidationError(
                "ID token iat is in the future",
            )

        if nonce is not None:
            token_nonce = claims.get("nonce")

            if token_nonce != nonce:
                raise IDTokenValidationError(
                    "ID token nonce mismatch",
                )

        if max_age_s is not None:
            auth_time = claims.get("auth_time")

            if not isinstance(
                auth_time,
                (int, float),
            ):
                raise IDTokenValidationError(
                    "auth_time required for max_age",
                )

            if now > auth_time + max_age_s + self.clock_skew_s:
                raise IDTokenValidationError(
                    "authentication is too old",
                )

        # When multiple audiences exist, OIDC requires
        # azp to identify the authorized party.
        audience = _audience_tuple(
            claims.get("aud"),
        )

        if len(audience) > 1:
            azp = claims.get("azp")

            if azp != self.client_id:
                raise IDTokenValidationError(
                    "invalid azp claim",
                )

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "OidcProvider must be used inside "
                "'async with' or supplied with http_client",
            )

        return self._client


def _required(
    payload: Mapping[str, Any],
    name: str,
) -> str:
    value = payload.get(name)

    if not isinstance(value, str) or not value:
        raise OIDCDiscoveryError(
            f"discovery metadata missing {name!r}",
        )

    return value


def _optional(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        return None

    return value


def _string_tuple(
    value: Any,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()

    return tuple(
        item
        for item in value
        if isinstance(item, str)
    )


def _audience_tuple(
    value: Any,
) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)

    if isinstance(value, list):
        return tuple(
            item
            for item in value
            if isinstance(item, str)
        )

    raise IDTokenValidationError(
        "invalid aud claim",
    )


def _json_dumps(
    value: Mapping[str, Any],
) -> str:
    return json.dumps(
        value,
        separators=(",", ":"),
    )