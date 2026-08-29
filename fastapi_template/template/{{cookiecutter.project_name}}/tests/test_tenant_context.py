"""Tenant authorization boundary: membership → TenantContext → resource."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.identity.principal import Anonymous, Principal
from {{cookiecutter.project_name}}.identity.tenant_context import (
    InMemoryMembershipRegistry,
    InMemoryResourceOwnershipRegistry,
    TenantContext,
    create_tenant_authorization,
)


def _authz():
    memberships = InMemoryMembershipRegistry()
    resources = InMemoryResourceOwnershipRegistry()
    return create_tenant_authorization(memberships, resources), memberships, resources


@pytest.mark.anyio
async def test_resolve_context_success() -> None:
    authz, memberships, _ = _authz()
    memberships.add_membership(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"editor"}),
    )
    principal = Principal(user_id="alice", provider="oidc")

    ctx = await authz.resolve_context(principal, org_id="org_a")

    assert ctx.org_id == "org_a"
    assert ctx.user_id == "alice"
    assert ctx.roles == frozenset({"editor"})
    assert ctx.is_active
    assert ctx.has_role("editor")
    assert ctx.has_permission("read")
    assert ctx.has_permission("write")


@pytest.mark.anyio
async def test_anonymous_resolve_context_401() -> None:
    authz, _, _ = _authz()

    with pytest.raises(Problem) as exc_info:
        await authz.resolve_context(Anonymous, org_id="org_a")

    assert exc_info.value.status_code == 401
    assert exc_info.value.title == "Not Authenticated"


@pytest.mark.anyio
async def test_no_membership_403() -> None:
    authz, _, _ = _authz()
    principal = Principal(user_id="bob")

    with pytest.raises(Problem) as exc_info:
        await authz.resolve_context(principal, org_id="org_a")

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Not A Member"


@pytest.mark.anyio
async def test_inactive_membership_403() -> None:
    authz, memberships, _ = _authz()
    memberships.add_membership(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"viewer"}),
    )
    assert memberships.deactivate(user_id="alice", org_id="org_a")
    principal = Principal(user_id="alice")

    with pytest.raises(Problem) as exc_info:
        await authz.resolve_context(principal, org_id="org_a")

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Not A Member"


@pytest.mark.anyio
async def test_authorize_resource_cross_tenant_403() -> None:
    authz, memberships, resources = _authz()
    memberships.add_membership(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"editor"}),
    )
    resources.register(resource_key="res:doc_b", org_id="org_b")
    principal = Principal(user_id="alice")
    ctx = await authz.resolve_context(principal, org_id="org_a")

    with pytest.raises(Problem) as exc_info:
        await authz.authorize_resource(
            ctx,
            resource_key="res:doc_b",
            permission="read",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Cross-Tenant Access Denied"


@pytest.mark.anyio
async def test_authorize_resource_missing_404() -> None:
    authz, memberships, _ = _authz()
    memberships.add_membership(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"editor"}),
    )
    principal = Principal(user_id="alice")
    ctx = await authz.resolve_context(principal, org_id="org_a")

    with pytest.raises(Problem) as exc_info:
        await authz.authorize_resource(
            ctx,
            resource_key="res:missing",
            permission="read",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.title == "Resource Not Found"


@pytest.mark.anyio
async def test_require_permission_success_and_fail() -> None:
    authz, memberships, resources = _authz()
    memberships.add_membership(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"viewer"}),
    )
    resources.register(resource_key="res:doc_a", org_id="org_a")
    principal = Principal(user_id="alice")
    ctx = await authz.resolve_context(principal, org_id="org_a")

    await authz.authorize_resource(
        ctx,
        resource_key="res:doc_a",
        permission="read",
    )
    ctx.require("read")

    with pytest.raises(Problem) as exc_info:
        ctx.require("write")

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Insufficient Permissions"


def test_is_service_preserved_through_has_permission() -> None:
    principal = Principal(
        user_id="svc:key_1",
        org_id="org_a",
        roles=frozenset({"viewer"}),
        provider="api_key",
        is_service=True,
    )
    ctx = TenantContext(
        principal=principal,
        org_id="org_a",
        roles=frozenset({"admin"}),
    )

    assert ctx.is_service is True
    assert ctx.has_permission("orders.refund") is True

    scoped = principal.with_org(ctx.org_id).with_roles(ctx.roles)
    assert scoped.is_service is True
    assert scoped.provider == "api_key"
    assert scoped.user_id == "svc:key_1"


def test_membership_registry_activate_deactivate_revoke_org() -> None:
    memberships = InMemoryMembershipRegistry()
    memberships.add_membership(
        user_id="alice",
        org_id="org_b",
        roles=frozenset({"editor"}),
    )
    memberships.add_membership(
        user_id="bob",
        org_id="org_b",
        roles=frozenset({"admin"}),
    )

    assert memberships.deactivate(user_id="alice", org_id="org_b")
    assert memberships.list_for_org("org_b") == [
        m for m in memberships.list_for_org("org_b") if m.user_id == "bob"
    ]
    assert len(memberships.list_for_org("org_b")) == 1

    assert memberships.activate(user_id="alice", org_id="org_b")
    assert len(memberships.list_for_org("org_b")) == 2

    affected = memberships.revoke_org("org_b")
    assert affected == 2
    assert memberships.list_for_org("org_b") == []
    assert memberships.list_for_user("alice") == []
