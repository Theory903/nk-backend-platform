"""RBAC capability authorization (not tenant / resource ownership).

Authorization is evaluated from the Principal's roles against
``ROLE_PERMISSIONS``. This answers:

    Can this principal perform ``orders.refund``?

It does **not** answer whether the principal may act on a specific
object or within a specific tenant. Keep PostgreSQL RLS (or equivalent)
as the tenant boundary; use a separate resource-auth layer for
object ownership.

Permission format:

    read
    write
    orders.read
    orders.refund
    orders.*

A global ``*`` permission grants everything.

This module performs capability authorization only. It does not perform
authentication, tenant isolation, or resource ownership checks.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from {{cookiecutter.project_name}}.identity.principal import Principal


ROLE_PERMISSIONS: Final = MappingProxyType(
    {
        "admin": frozenset({"*"}),
        "owner": frozenset(
            {
                "read",
                "write",
                "delete",
                "admin.read",
                "files.read",
                "files.write",
                "files.delete",
            }
        ),
        "editor": frozenset(
            {
                "read",
                "write",
                "files.read",
                "files.write",
            }
        ),
        "viewer": frozenset(
            {
                "read",
                "files.read",
            }
        ),
    }
)


def permissions_for(
    principal: Principal,
) -> frozenset[str]:
    """Return the effective permissions granted by the principal's roles."""

    permissions: set[str] = set()

    for role in principal.roles:
        permissions.update(
            ROLE_PERMISSIONS.get(
                role,
                frozenset(),
            )
        )

    return frozenset(permissions)


def _permission_matches(
    granted: str,
    required: str,
) -> bool:
    """Return whether one granted permission covers a required permission."""

    if granted == "*":
        return True

    if granted == required:
        return True

    if not granted.endswith(".*"):
        return False

    prefix = granted[:-2]

    return (
        bool(prefix)
        and required.startswith(prefix + ".")
    )


def has_permission(
    principal: Principal,
    required: str,
) -> bool:
    """Return whether the principal has the requested permission."""

    if principal.is_anonymous:
        return False

    required = required.strip()

    if not required:
        return False

    for granted in permissions_for(principal):
        if _permission_matches(
            granted,
            required,
        ):
            return True

    return False


__all__ = [
    "ROLE_PERMISSIONS",
    "permissions_for",
    "has_permission",
]
