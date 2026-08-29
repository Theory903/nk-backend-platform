"""Unit tests for identity RBAC capability checks."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.identity.permissions import (
    ROLE_PERMISSIONS,
    _permission_matches,
    has_permission,
    permissions_for,
)
from {{cookiecutter.project_name}}.identity.principal import Principal


def _principal(*roles: str) -> Principal:
    return Principal(user_id="u1", roles=frozenset(roles))


def test_viewer_can_read_not_write() -> None:
    p = _principal("viewer")
    assert has_permission(p, "read")
    assert has_permission(p, "files.read")
    assert not has_permission(p, "write")
    assert not has_permission(p, "delete")
    assert not has_permission(p, "files.write")
    assert permissions_for(p) == frozenset({"read", "files.read"})


def test_editor_can_write() -> None:
    p = _principal("editor")
    assert has_permission(p, "read")
    assert has_permission(p, "write")
    assert has_permission(p, "files.write")
    assert not has_permission(p, "delete")
    assert not has_permission(p, "files.delete")


def test_owner_matrix() -> None:
    p = _principal("owner")
    assert has_permission(p, "read")
    assert has_permission(p, "write")
    assert has_permission(p, "delete")
    assert has_permission(p, "admin.read")
    assert has_permission(p, "files.read")
    assert has_permission(p, "files.write")
    assert has_permission(p, "files.delete")
    assert not has_permission(p, "orders.refund")


def test_admin_star_matches_anything() -> None:
    p = _principal("admin")
    assert has_permission(p, "read")
    assert has_permission(p, "orders.refund")
    assert has_permission(p, "anything.nested.deep")
    assert permissions_for(p) == frozenset({"*"})


def test_permission_matches_prefix_wildcard() -> None:
    assert _permission_matches("orders.*", "orders.refund")
    assert _permission_matches("orders.*", "orders.read")
    assert not _permission_matches("orders.*", "orders")
    assert not _permission_matches("orders.*", "billing.refund")
    assert not _permission_matches(".*", "orders.refund")


def test_permission_matches_exact_and_global() -> None:
    assert _permission_matches("*", "anything")
    assert _permission_matches("read", "read")
    assert not _permission_matches("read", "write")


def test_anonymous_denied() -> None:
    p = Principal(user_id="")
    assert p.is_anonymous
    assert not has_permission(p, "read")
    assert permissions_for(p) == frozenset()


def test_empty_permission_denied() -> None:
    p = _principal("admin")
    assert not has_permission(p, "")
    assert not has_permission(p, "   ")


def test_role_permissions_immutable() -> None:
    with pytest.raises(TypeError):
        ROLE_PERMISSIONS["admin"] = frozenset({"read"})  # type: ignore[index]

    with pytest.raises(AttributeError):
        ROLE_PERMISSIONS["admin"].add("write")  # type: ignore[attr-defined]


def test_unknown_role_grants_nothing() -> None:
    p = _principal("unknown_role")
    assert permissions_for(p) == frozenset()
    assert not has_permission(p, "read")
