import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from {{cookiecutter.project_name}}.identity.token_policy import (
    TokenPolicy,
    create_token,
    validate_token,
)
from {{cookiecutter.project_name}}.identity.jwt import decode_hs256, encode_hs256
from {{cookiecutter.project_name}}.identity.mfa import generate_secret, provisioning_uri, totp, verify_totp
from {{cookiecutter.project_name}}.identity.session import SessionStore
from {{cookiecutter.project_name}}.identity.providers.magic_link import (
    InMemoryMagicLinkStore,
    MagicLinkProvider,
    RedisMagicLinkStore,
)
from {{cookiecutter.project_name}}.identity.providers.oauth2 import generate_pkce_pair, generate_state, OAuth2Client
from {{cookiecutter.project_name}}.identity.providers.oidc import OidcProvider
from {{cookiecutter.project_name}}.identity.providers.ldap_provider import LdapIdentityProvider, MockLdapBackend


# --- JWT ---

def test_jwt_hs256_roundtrip() -> None:
    claims = {"sub": "u1", "exp": 9999999999}
    token = encode_hs256(claims, "secret")
    decoded = decode_hs256(token, "secret")
    assert decoded is not None
    assert decoded["sub"] == "u1"


def test_jwt_wrong_secret() -> None:
    token = encode_hs256({"sub": "u"}, "right")
    assert decode_hs256(token, "wrong") is None


def test_jwt_expired() -> None:
    token = encode_hs256({"sub": "u", "exp": 1}, "k")
    assert decode_hs256(token, "k") is None


def test_create_access_token_with_extra_claims() -> None:
    policy = TokenPolicy()
    secret = "all-auth-jwt-test-secret-32bytes!!"
    token = create_token("user_1", secret, expires_in_s=300, extra_claims={"org_id": "org_1"})
    result = validate_token(token, secret, policy=policy)
    assert result.valid
    assert result.claims.get("org_id") == "org_1"


# --- TOTP MFA ---

def test_totp_roundtrip() -> None:
    secret = generate_secret()
    code = totp(secret)
    assert len(code) == 6
    assert verify_totp(secret, code) is True


def test_totp_rejects_bad_code() -> None:
    secret = generate_secret()
    assert not verify_totp(secret, "000000")


def test_provisioning_uri_format() -> None:
    secret = generate_secret()
    uri = provisioning_uri(secret, "user@x.com", issuer="MyApp")
    assert "otpauth://totp/MyApp:" in uri
    assert f"secret={secret.upper()}" in uri


# --- Session store ---

def test_session_lifecycle() -> None:
    store = SessionStore(default_ttl_s=300)
    sid = store.create("user_1", {"role": "admin"})
    session = store.get(sid)
    assert session is not None
    assert session["principal_id"] == "user_1"
    assert session["data"]["role"] == "admin"


def test_session_expiry() -> None:
    from unittest.mock import patch

    store = SessionStore(default_ttl_s=1, idle_timeout_s=1)
    sid = store.create("u")
    session = store.get_session(sid, touch=False)
    assert session is not None
    with patch(
        "{{cookiecutter.project_name}}.identity.session.time.time",
        return_value=session.expires_at + 0.1,
    ):
        assert store.get(sid) is None


def test_session_revocation() -> None:
    store = SessionStore()
    sid = store.create("u")
    assert store.revoke(sid) is True
    assert store.get(sid) is None


def test_list_sessions_for_principal() -> None:
    store = SessionStore()
    s1 = store.create("alice")
    s2 = store.create("alice")
    s3 = store.create("bob")
    alice_ids = {s.session_id for s in store.list_for_principal("alice")}
    assert alice_ids == {s1, s2}
    assert s3 not in alice_ids


# --- OAuth2 ---

def test_pkce_pair_generation() -> None:
    pair = generate_pkce_pair()
    assert len(pair.verifier) >= 43
    assert len(pair.challenge) >= 43
    assert pair.verifier != pair.challenge
    assert pair.method == "S256"


def test_authorization_url_includes_params() -> None:
    client = OAuth2Client(
        client_id="cid", client_secret="cs",
        authorize_url="https://idp.example.com/auth",
        token_url="https://idp.example.com/token",
        redirect_uri="https://app.example.com/cb",
        scopes=["openid", "profile"],
    )
    url, transaction = client.begin_authorization(use_pkce=False)
    assert "response_type=code" in url
    assert "client_id=cid" in url
    assert f"state={transaction.state}" in url
    assert "scope=openid+profile" in url or "scope=openid%20profile" in url
    assert generate_state()  # still exported for callers


def test_pkce_url_has_challenge() -> None:
    client = OAuth2Client(
        client_id="cid", client_secret="cs",
        authorize_url="https://idp.example.com/auth",
        token_url="https://idp.example.com/token",
        redirect_uri="https://app.example.com/cb",
    )
    url, transaction = client.begin_authorization(use_pkce=True)
    assert transaction.pkce is not None
    assert "code_challenge=" in url
    assert transaction.pkce.challenge in url
    assert "code_challenge_method=S256" in url


def test_oidc_provider_wires_alongside_oauth2() -> None:
    """OAuth2 handles code exchange; OidcProvider validates id_token signatures."""
    oauth = OAuth2Client(
        client_id="cid",
        client_secret="cs",
        authorize_url="https://idp.example.com/auth",
        token_url="https://idp.example.com/token",
        redirect_uri="https://app.example.com/cb",
        scopes=["openid"],
    )
    oidc = OidcProvider(
        issuer_url="https://idp.example.com",
        client_id="cid",
    )
    assert oauth.client_id == oidc.client_id
    assert oidc.issuer_url == "https://idp.example.com"


# --- LDAP ---

@pytest.mark.asyncio
async def test_ldap_auth_success() -> None:
    backend = MockLdapBackend(
        users={
            "jane": {
                "password": "pass123",
                "user_id": "jane",
                "display_name": "Jane",
            },
        },
    )
    provider = LdapIdentityProvider(backend=backend)
    result = await provider.authenticate({"username": "jane", "password": "pass123"})
    assert result is not None
    assert result["provider"] == "ldap"
    assert result["user_id"] == "jane"


@pytest.mark.asyncio
async def test_ldap_auth_failure() -> None:
    backend = MockLdapBackend(
        users={"jane": {"password": "pass123"}},
    )
    provider = LdapIdentityProvider(backend=backend)
    assert await provider.authenticate({"username": "jane", "password": "wrong"}) is None
    assert await provider.authenticate({}) is None


# --- Magic Link ---

@pytest.mark.asyncio
async def test_magic_link_roundtrip() -> None:
    provider = MagicLinkProvider(secret="link-secret", ttl_s=300)
    token = provider.create_link_token("User@Example.com")
    email = await provider.verify(token)
    assert email == "user@example.com"


@pytest.mark.asyncio
async def test_magic_link_single_use() -> None:
    store = InMemoryMagicLinkStore()
    provider = MagicLinkProvider(secret="s", ttl_s=300, store=store)
    token = provider.create_link_token("a@b.c")
    assert await provider.verify(token) == "a@b.c"
    assert await provider.verify(token) is None  # replay blocked via store.consume


@pytest.mark.asyncio
async def test_magic_link_tampered() -> None:
    provider = MagicLinkProvider(secret="s", ttl_s=300)
    token = provider.create_link_token("a@b.c")
    tampered = token[:-4] + "XXXX"
    assert await provider.verify(tampered) is None


@pytest.mark.asyncio
async def test_magic_link_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = MagicLinkProvider(secret="s", ttl_s=60)
    token = provider.create_link_token("a@b.c")
    real_time = time.time
    monkeypatch.setattr(
        "{{cookiecutter.project_name}}.identity.providers.magic_link.time.time",
        lambda: real_time() + 120,
    )
    assert await provider.verify(token) is None


def test_magic_link_invalid_email() -> None:
    provider = MagicLinkProvider(secret="s", ttl_s=300)
    with pytest.raises(ValueError, match="invalid email"):
        provider.create_link_token("not-an-email")
    with pytest.raises(ValueError, match="invalid email"):
        provider.create_link_token("")


def test_magic_link_empty_secret() -> None:
    with pytest.raises(ValueError, match="secret cannot be empty"):
        MagicLinkProvider(secret="")


@pytest.mark.asyncio
async def test_redis_magic_link_store_set_nx() -> None:
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    store = RedisMagicLinkStore(redis, key_prefix="ml:")
    assert await store.consume("tid-1", ttl_s=300) is True
    redis.set.assert_awaited_once_with("ml:tid-1", "1", nx=True, ex=300)

    redis.set = AsyncMock(return_value=None)
    assert await store.consume("tid-1", ttl_s=300) is False
