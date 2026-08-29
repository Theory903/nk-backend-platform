"""Tests for the immutable identity Principal."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.identity import deps as auth_deps
from {{cookiecutter.project_name}}.identity.principal import Anonymous, Principal


def test_anonymous_semantics() -> None:
    assert Anonymous.is_anonymous is True
    assert Anonymous.is_authenticated is False
    assert Anonymous.user_id == ""
    assert Anonymous.org_id is None
    assert Anonymous.roles == frozenset()
    assert Anonymous.provider == "local"
    assert Anonymous.is_service is False
    assert Anonymous.is_tenant_scoped is False


def test_anonymous_unified_with_deps() -> None:
    assert auth_deps.Anonymous is Anonymous
    assert auth_deps.Anonymous.is_anonymous is True


def test_authenticated_and_tenant_scoped() -> None:
    p = Principal(user_id="alice", org_id="org_a", roles=frozenset({"admin"}))
    assert p.is_authenticated is True
    assert p.is_anonymous is False
    assert p.is_tenant_scoped is True
    assert p.require_org() == "org_a"


def test_strip_normalize_user_provider_roles() -> None:
    p = Principal(
        user_id="  alice  ",
        roles=frozenset({"  admin ", "", "  ", "reader"}),
        provider="  oidc  ",
    )
    assert p.user_id == "alice"
    assert p.roles == frozenset({"admin", "reader"})
    assert p.provider == "oidc"


def test_empty_org_id_strip_becomes_none() -> None:
    p = Principal(user_id="alice", org_id="   ")
    assert p.org_id is None
    assert p.is_tenant_scoped is False


def test_empty_provider_falls_back_to_local() -> None:
    p = Principal(user_id="alice", provider="   ")
    assert p.provider == "local"


def test_has_role_any_all() -> None:
    p = Principal(
        user_id="alice",
        roles=frozenset({"admin", "reader", "billing"}),
    )
    assert p.has_role("admin") is True
    assert p.has_role("missing") is False
    assert p.has_any_role("missing", "reader") is True
    assert p.has_any_role("missing", "other") is False
    assert p.has_all_roles("admin", "reader") is True
    assert p.has_all_roles("admin", "missing") is False


def test_require_org_raises_without_org() -> None:
    p = Principal(user_id="alice")
    with pytest.raises(ValueError, match="no organization scope"):
        p.require_org()


def test_with_roles_immutability() -> None:
    original = Principal(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"reader"}),
        provider="local",
        is_service=False,
    )
    updated = original.with_roles(["admin", "  writer  ", ""])

    assert original.roles == frozenset({"reader"})
    assert updated.roles == frozenset({"admin", "writer"})
    assert updated.user_id == "alice"
    assert updated.org_id == "org_a"
    assert updated is not original


def test_with_org_immutability() -> None:
    original = Principal(user_id="alice", org_id="org_a")
    updated = original.with_org("org_b")
    cleared = original.with_org(None)

    assert original.org_id == "org_a"
    assert updated.org_id == "org_b"
    assert cleared.org_id is None
    assert updated is not original


def test_service_principal_flag() -> None:
    p = Principal(
        user_id="svc:key-1",
        roles=frozenset({"service"}),
        provider="api_key",
        is_service=True,
    )
    assert p.is_service is True
    assert p.is_authenticated is True
    assert p.has_role("service") is True


def test_frozen_slots() -> None:
    p = Principal(user_id="alice")
    with pytest.raises(Exception):
        p.user_id = "bob"  # type: ignore[misc]
    assert not hasattr(p, "__dict__")
