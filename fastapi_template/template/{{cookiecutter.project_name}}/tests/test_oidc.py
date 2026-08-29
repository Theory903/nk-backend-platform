"""OidcProvider ID-token signature validation tests (mocked discovery + JWKS)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from {{cookiecutter.project_name}}.identity.providers.oidc import (
    IDTokenValidationError,
    OIDCKeyError,
    OidcProvider,
)

ISSUER = "https://idp.example.com"
CLIENT_ID = "my-client"
KID = "test-key-1"


@pytest.fixture
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_jwk = json.loads(
        RSAAlgorithm.to_jwk(private_key.public_key()),
    )
    public_jwk["kid"] = KID
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"
    return private_key, public_jwk


def _discovery() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/auth",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "id_token_signing_alg_values_supported": ["RS256"],
    }


def _sign(
    private_key: rsa.RSAPrivateKey,
    claims: dict[str, Any],
    *,
    kid: str = KID,
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(
        claims,
        private_key,
        algorithm=algorithm,
        headers={"kid": kid, "alg": algorithm},
    )


def _base_claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": "user-1",
        "aud": CLIENT_ID,
        "exp": now + 600,
        "iat": now,
        "nonce": "expected-nonce",
    }
    claims.update(overrides)
    return claims


def _mock_client(
    *,
    jwks: dict[str, Any],
    discovery: dict[str, Any] | None = None,
    refresh_jwks: dict[str, Any] | None = None,
) -> httpx.AsyncClient:
    discovery = discovery or _discovery()
    jwks_hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=discovery)
        if path.endswith("/jwks"):
            jwks_hits["n"] += 1
            body = (
                refresh_jwks
                if refresh_jwks is not None and jwks_hits["n"] > 1
                else jwks
            )
            return httpx.Response(200, json=body)
        if path.endswith("/userinfo"):
            return httpx.Response(
                200,
                json={"sub": "user-1", "email": "u@example.com"},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=ISSUER,
    )


def _provider(http_client: httpx.AsyncClient) -> OidcProvider:
    return OidcProvider(
        issuer_url=ISSUER,
        client_id=CLIENT_ID,
        http_client=http_client,
        clock_skew_s=60,
    )


@pytest.mark.anyio
async def test_valid_id_token(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(private_key, _base_claims())
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        validated = await provider.validate_id_token(
            token,
            nonce="expected-nonce",
        )

    assert validated.subject == "user-1"
    assert validated.issuer == ISSUER
    assert validated.audience == (CLIENT_ID,)
    assert validated.email is None
    assert validated.nonce == "expected-nonce"


@pytest.mark.anyio
async def test_wrong_audience_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(private_key, _base_claims(aud="other-client"))
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        with pytest.raises(IDTokenValidationError):
            await provider.validate_id_token(token)


@pytest.mark.anyio
async def test_wrong_issuer_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(
        private_key,
        _base_claims(iss="https://evil.example.com"),
    )
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        with pytest.raises(IDTokenValidationError):
            await provider.validate_id_token(token)


@pytest.mark.anyio
async def test_bad_signature_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    other_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    token = _sign(other_key, _base_claims())
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        with pytest.raises(IDTokenValidationError):
            await provider.validate_id_token(token)


@pytest.mark.anyio
async def test_unknown_kid_triggers_jwks_refresh(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    rotated = dict(public_jwk)
    rotated["kid"] = "rotated-kid"
    token = _sign(
        private_key,
        _base_claims(),
        kid="rotated-kid",
    )
    client = _mock_client(
        jwks={"keys": [public_jwk]},
        refresh_jwks={"keys": [rotated]},
    )

    async with client:
        provider = _provider(client)
        # Prime cache with old JWKS (missing rotated kid).
        await provider.get_jwks()
        validated = await provider.validate_id_token(
            token,
            nonce="expected-nonce",
        )

    assert validated.subject == "user-1"


@pytest.mark.anyio
async def test_nonce_mismatch_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(private_key, _base_claims(nonce="token-nonce"))
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        with pytest.raises(IDTokenValidationError, match="nonce"):
            await provider.validate_id_token(
                token,
                nonce="expected-nonce",
            )


@pytest.mark.anyio
async def test_alg_not_allowed_rejected(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(private_key, _base_claims())
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = OidcProvider(
            issuer_url=ISSUER,
            client_id=CLIENT_ID,
            http_client=client,
            allowed_algorithms=("ES256",),
        )
        with pytest.raises(IDTokenValidationError, match="algorithm"):
            await provider.validate_id_token(token)


@pytest.mark.anyio
async def test_azp_required_for_multi_audience(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(
        private_key,
        _base_claims(
            aud=[CLIENT_ID, "other-aud"],
            azp=CLIENT_ID,
        ),
    )
    bad_token = _sign(
        private_key,
        _base_claims(
            aud=[CLIENT_ID, "other-aud"],
            azp="wrong-client",
        ),
    )
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        ok = await provider.validate_id_token(
            token,
            nonce="expected-nonce",
        )
        assert ok.audience == (CLIENT_ID, "other-aud")

        with pytest.raises(IDTokenValidationError, match="azp"):
            await provider.validate_id_token(
                bad_token,
                nonce="expected-nonce",
            )


@pytest.mark.anyio
async def test_unknown_kid_after_refresh_raises_key_error(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, public_jwk = rsa_keypair
    token = _sign(private_key, _base_claims(), kid="missing-kid")
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        with pytest.raises(OIDCKeyError, match="missing-kid"):
            await provider.validate_id_token(token)


@pytest.mark.anyio
async def test_userinfo(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    _, public_jwk = rsa_keypair
    client = _mock_client(jwks={"keys": [public_jwk]})

    async with client:
        provider = _provider(client)
        info = await provider.get_userinfo("access-token")

    assert info["sub"] == "user-1"
    assert info["email"] == "u@example.com"


def test_rsa_pem_roundtrip_sanity(
    rsa_keypair: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    """Ensure cryptography key material is usable (signature path dependency)."""
    private_key, _ = rsa_keypair
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    assert b"PRIVATE KEY" in pem
