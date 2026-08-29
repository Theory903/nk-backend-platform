"""Platform tenancy deps: X-Org-Id is a selector, never an authorizer."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.identity.principal import Anonymous, Principal
from {{cookiecutter.project_name}}.identity.tenant_context import (
    InMemoryMembershipRegistry,
    InMemoryResourceOwnershipRegistry,
    create_tenant_authorization,
)
from {{cookiecutter.project_name}}.platform import tenancy
from {{cookiecutter.project_name}}.platform.tenancy import (
    configure_tenant_authorization,
    get_requested_org_id,
    get_tenant_authorization,
    require_org_id,
    require_tenant_context,
)


@pytest.fixture(autouse=True)
def _reset_tenant_authz() -> None:
    """Isolate process-scoped DI across tests."""
    tenancy._tenant_authorization = None
    yield
    tenancy._tenant_authorization = None


@pytest.fixture
def memberships() -> InMemoryMembershipRegistry:
    return InMemoryMembershipRegistry()


@pytest.fixture
def authz(memberships: InMemoryMembershipRegistry):
    service = create_tenant_authorization(
        memberships,
        InMemoryResourceOwnershipRegistry(),
    )
    configure_tenant_authorization(service)
    return service


# ---------------------------------------------------------------------------
# get_requested_org_id — header only
# ---------------------------------------------------------------------------


def test_get_requested_org_id_strips_and_empty() -> None:
    assert get_requested_org_id("  org_a  ") == "org_a"
    assert get_requested_org_id("   ") is None
    assert get_requested_org_id(None) is None


# ---------------------------------------------------------------------------
# require_org_id — principal.org_id authoritative
# ---------------------------------------------------------------------------


def test_require_org_id_anonymous_401() -> None:
    with pytest.raises(Problem) as exc_info:
        require_org_id(requested_org_id="org_a", principal=Anonymous)

    assert exc_info.value.status_code == 401
    assert exc_info.value.title == "Not Authenticated"


def test_require_org_id_no_principal_org_403() -> None:
    principal = Principal(user_id="alice")

    with pytest.raises(Problem) as exc_info:
        require_org_id(requested_org_id=None, principal=principal)

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Organization Required"


def test_require_org_id_mismatch_403() -> None:
    principal = Principal(user_id="alice", org_id="org_a")

    with pytest.raises(Problem) as exc_info:
        require_org_id(requested_org_id="org_b", principal=principal)

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Organization Mismatch"


def test_require_org_id_match_returns_principal_org() -> None:
    principal = Principal(user_id="alice", org_id="org_a")

    assert (
        require_org_id(requested_org_id="org_a", principal=principal)
        == "org_a"
    )
    assert (
        require_org_id(requested_org_id=None, principal=principal)
        == "org_a"
    )


# ---------------------------------------------------------------------------
# require_tenant_context — membership validated
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_require_tenant_context_anonymous_401(
    authz,
) -> None:
    with pytest.raises(Problem) as exc_info:
        await require_tenant_context(
            principal=Anonymous,
            requested_org_id="org_a",
            authz=authz,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_require_tenant_context_no_org_400(
    authz,
) -> None:
    principal = Principal(user_id="alice")

    with pytest.raises(Problem) as exc_info:
        await require_tenant_context(
            principal=principal,
            requested_org_id=None,
            authz=authz,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.title == "Organization Required"


@pytest.mark.anyio
async def test_require_tenant_context_member_of_requested_org(
    authz,
    memberships: InMemoryMembershipRegistry,
) -> None:
    memberships.add_membership(
        user_id="alice",
        org_id="org_b",
        roles=frozenset({"editor"}),
    )
    # principal default org is A; request selects B (multi-org path)
    principal = Principal(user_id="alice", org_id="org_a")

    ctx = await require_tenant_context(
        principal=principal,
        requested_org_id="org_b",
        authz=authz,
    )

    assert ctx.org_id == "org_b"
    assert ctx.user_id == "alice"
    assert ctx.has_role("editor")


@pytest.mark.anyio
async def test_require_tenant_context_falls_back_to_principal_org(
    authz,
    memberships: InMemoryMembershipRegistry,
) -> None:
    memberships.add_membership(
        user_id="alice",
        org_id="org_a",
        roles=frozenset({"viewer"}),
    )
    principal = Principal(user_id="alice", org_id="org_a")

    ctx = await require_tenant_context(
        principal=principal,
        requested_org_id=None,
        authz=authz,
    )

    assert ctx.org_id == "org_a"


@pytest.mark.anyio
async def test_require_tenant_context_not_a_member_403(
    authz,
) -> None:
    principal = Principal(user_id="bob", org_id="org_a")

    with pytest.raises(Problem) as exc_info:
        await require_tenant_context(
            principal=principal,
            requested_org_id="org_b",
            authz=authz,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Not A Member"


@pytest.mark.anyio
async def test_header_alone_never_grants_tenant_context(
    authz,
) -> None:
    """Authenticated user + X-Org-Id without membership must not succeed."""
    principal = Principal(user_id="eve")  # no org_id, no membership

    with pytest.raises(Problem) as exc_info:
        await require_tenant_context(
            principal=principal,
            requested_org_id="org_secret",
            authz=authz,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.title == "Not A Member"


def test_get_tenant_authorization_requires_configure() -> None:
    with pytest.raises(Problem) as exc_info:
        get_tenant_authorization()

    assert exc_info.value.status_code == 500
