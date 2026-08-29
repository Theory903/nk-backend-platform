"""LDAP identity provider tests (MockLdapBackend + filter escaping)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from {{cookiecutter.project_name}}.identity.providers.ldap_provider import (
    Ldap3Backend,
    LdapConfig,
    LdapIdentityProvider,
    MockLdapBackend,
)


def _sample_users() -> dict:
    return {
        "jane": {
            "password": "pass123",
            "user_id": "guid-jane",
            "display_name": "Jane Doe",
            "email": "jane@example.com",
            "groups": ("cn=eng,ou=groups,dc=example,dc=com",),
            "dn": "cn=jane,ou=users,dc=example,dc=com",
        },
    }


def _install_fake_ldap3_escape(escape_fn):
    """Install a minimal ldap3.utils.conv stub when ldap3 is not installed."""
    conv = types.ModuleType("ldap3.utils.conv")
    conv.escape_filter_chars = escape_fn  # type: ignore[attr-defined]
    utils = types.ModuleType("ldap3.utils")
    utils.conv = conv  # type: ignore[attr-defined]
    ldap3_mod = types.ModuleType("ldap3")
    ldap3_mod.utils = utils  # type: ignore[attr-defined]
    return patch.dict(
        sys.modules,
        {
            "ldap3": ldap3_mod,
            "ldap3.utils": utils,
            "ldap3.utils.conv": conv,
        },
    )


@pytest.mark.anyio
async def test_ldap_auth_success() -> None:
    backend = MockLdapBackend(users=_sample_users())
    provider = LdapIdentityProvider(backend=backend)

    result = await provider.authenticate(
        {"username": "jane", "password": "pass123"},
    )

    assert result is not None
    assert result["provider"] == "ldap"
    assert result["user_id"] == "guid-jane"
    assert result["username"] == "jane"
    assert result["display_name"] == "Jane Doe"
    assert result["email"] == "jane@example.com"
    assert result["groups"] == [
        "cn=eng,ou=groups,dc=example,dc=com",
    ]
    assert result["dn"] == "cn=jane,ou=users,dc=example,dc=com"
    assert backend.bound == ["jane"]


@pytest.mark.anyio
async def test_ldap_auth_failure_wrong_password() -> None:
    backend = MockLdapBackend(users=_sample_users())
    provider = LdapIdentityProvider(backend=backend)

    assert (
        await provider.authenticate(
            {"username": "jane", "password": "wrong"},
        )
        is None
    )


@pytest.mark.anyio
async def test_ldap_auth_failure_unknown_user() -> None:
    backend = MockLdapBackend(users=_sample_users())
    provider = LdapIdentityProvider(backend=backend)

    assert (
        await provider.authenticate(
            {"username": "nobody", "password": "pass123"},
        )
        is None
    )


@pytest.mark.anyio
async def test_ldap_auth_empty_password_rejected() -> None:
    backend = MockLdapBackend(users=_sample_users())
    provider = LdapIdentityProvider(backend=backend)

    assert (
        await provider.authenticate(
            {"username": "jane", "password": ""},
        )
        is None
    )
    # Missing / non-string password
    assert await provider.authenticate({"username": "jane"}) is None
    assert (
        await provider.authenticate(
            {"username": "jane", "password": 123},  # type: ignore[dict-item]
        )
        is None
    )
    assert await provider.authenticate({}) is None


@pytest.mark.anyio
async def test_ldap_identity_shape() -> None:
    backend = MockLdapBackend(users=_sample_users())
    provider = LdapIdentityProvider(backend=backend)
    result = await provider.authenticate(
        {"username": "jane", "password": "pass123"},
    )
    assert result is not None
    assert set(result) >= {
        "user_id",
        "username",
        "provider",
        "display_name",
        "email",
        "groups",
        "dn",
    }


@pytest.mark.anyio
async def test_ldap_backend_rejects_empty_password() -> None:
    """Production backend short-circuits empty credentials."""
    backend = Ldap3Backend(LdapConfig())
    assert await backend.authenticate("jane", "") is None
    assert await backend.authenticate("", "x") is None


def test_build_user_filter_escapes_special_chars() -> None:
    """Username filter injection is blocked via escape_filter_chars."""
    backend = Ldap3Backend(LdapConfig())
    malicious = "admin)(|(uid=*"
    calls: list[str] = []

    def fake_escape(value: str) -> str:
        calls.append(value)
        return f"ESCAPED<{value}>"

    with _install_fake_ldap3_escape(fake_escape):
        filter_str = backend.build_user_filter(malicious)

    assert calls == [malicious]
    assert "ESCAPED<" in filter_str
    assert "ESCAPED<" + malicious + ">" in filter_str or f"ESCAPED<{malicious}>" in filter_str
    assert "{username}" not in filter_str
    # Raw username must not be interpolated without going through escape
    assert filter_str.count("ESCAPED<") == 3  # uid, sAMAccountName, UPN

def test_build_user_filter_uses_escaped_value_in_format() -> None:
    backend = Ldap3Backend(
        LdapConfig(user_filter="(uid={username})"),
    )

    with _install_fake_ldap3_escape(lambda _value: "safe_user"):
        assert backend.build_user_filter("raw*)(uid=*") == "(uid=safe_user)"


@pytest.mark.anyio
async def test_lookup_passes_escaped_filter_to_search() -> None:
    """_lookup_bound_user must not pass raw username into search_filter."""
    backend = Ldap3Backend(
        LdapConfig(user_filter="(sAMAccountName={username})"),
    )
    connection = MagicMock()
    connection.search.return_value = False
    connection.entries = []

    with _install_fake_ldap3_escape(lambda _value: "escaped_name"):
        await backend._lookup_bound_user(connection, "raw*)(cn=*")

    _args, kwargs = connection.search.call_args
    assert kwargs["search_filter"] == "(sAMAccountName=escaped_name)"
    assert "raw*" not in kwargs["search_filter"]
