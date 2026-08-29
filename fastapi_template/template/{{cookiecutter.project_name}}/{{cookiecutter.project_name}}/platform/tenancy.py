"""
Organization context dependencies.

The authenticated Principal is the authority for tenant identity.

X-Org-Id is treated only as a requested organization selector and MUST
never grant access by itself.

Resolution flow:

    Authentication
        ↓
    Principal
        ↓
    requested X-Org-Id
        ↓
    membership validation (TenantAuthorizationService)
        ↓
    TenantContext
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.identity.deps import CurrentUser
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.identity.tenant_context import (
    InMemoryResourceOwnershipRegistry,
    MembershipResolver,
    ResourceOwnershipResolver,
    TenantAuthorizationService,
    TenantContext,
    create_tenant_authorization,
)

# ---------------------------------------------------------------------------
# Process-scoped tenant authorization (DI)
# ---------------------------------------------------------------------------

_tenant_authorization: TenantAuthorizationService | None = None


def configure_tenant_authorization(
    service: TenantAuthorizationService | None = None,
    *,
    memberships: MembershipResolver | None = None,
    resources: ResourceOwnershipResolver | None = None,
) -> TenantAuthorizationService:
    """
    Install the process-scoped TenantAuthorizationService.

    Pass either a fully built ``service``, or ``memberships`` (and optional
    ``resources``) to construct one via ``create_tenant_authorization``.
    """
    global _tenant_authorization

    if service is not None:
        _tenant_authorization = service
        return service

    if memberships is None:
        raise ValueError(
            "configure_tenant_authorization requires service= or memberships="
        )

    built = create_tenant_authorization(
        memberships,
        resources or InMemoryResourceOwnershipRegistry(),
    )
    _tenant_authorization = built
    return built


def get_tenant_authorization() -> TenantAuthorizationService:
    """FastAPI dependency: return the configured tenant authorization boundary."""
    if _tenant_authorization is None:
        raise Problem(
            title="Tenant Authorization Not Configured",
            status_code=500,
            detail=(
                "call configure_tenant_authorization(...) "
                "during application startup"
            ),
        )
    return _tenant_authorization


def get_membership_registry() -> MembershipResolver:
    """
    Stub for callers that want the raw MembershipResolver.

    Prefer ``get_tenant_authorization`` / ``configure_tenant_authorization``.
    """
    raise NotImplementedError(
        "inject via configure_tenant_authorization(memberships=...); "
        "do not invent a production MembershipRegistry here"
    )


# ---------------------------------------------------------------------------
# Header selector (NOT authorization)
# ---------------------------------------------------------------------------


def get_requested_org_id(
    x_org_id: Annotated[
        str | None,
        Header(alias="X-Org-Id"),
    ] = None,
) -> str | None:
    """
    Return the organization explicitly requested by the client.

    This is NOT an authorization decision.
    """
    if x_org_id is None:
        return None

    value = x_org_id.strip()

    return value or None


# ---------------------------------------------------------------------------
# Single-org: principal.org_id is authoritative
# ---------------------------------------------------------------------------


def require_org_id(
    requested_org_id: Annotated[
        str | None,
        Depends(get_requested_org_id),
    ],
    principal: Annotated[
        Principal,
        Depends(CurrentUser),
    ],
) -> str:
    """
    Resolve the effective organization for single-org principals.

    The principal's org_id is authoritative.

    X-Org-Id may only match the authenticated organization; a mismatch
    yields 403. The header alone never grants access.
    """
    if principal.is_anonymous:
        raise Problem(
            title="Not Authenticated",
            status_code=401,
            detail="authentication required",
        )

    principal_org_id = principal.org_id

    if not principal_org_id:
        raise Problem(
            title="Organization Required",
            status_code=403,
            detail="principal has no active organization",
        )

    if (
        requested_org_id is not None
        and requested_org_id != principal_org_id
    ):
        raise Problem(
            title="Organization Mismatch",
            status_code=403,
            detail="requested organization is not the authenticated organization",
        )

    return principal_org_id


# ---------------------------------------------------------------------------
# Multi-org: membership-validated TenantContext
# ---------------------------------------------------------------------------


async def require_tenant_context(
    principal: Annotated[
        Principal,
        Depends(CurrentUser),
    ],
    requested_org_id: Annotated[
        str | None,
        Depends(get_requested_org_id),
    ],
    authz: Annotated[
        TenantAuthorizationService,
        Depends(get_tenant_authorization),
    ],
) -> TenantContext:
    """
    Resolve a membership-validated TenantContext.

    Selection order:
        1. X-Org-Id when present (request only — not authorization)
        2. principal.org_id as fallback

    Access is granted only after TenantAuthorizationService.resolve_context
    confirms active membership. The header alone never authorizes.
    """
    if principal.is_anonymous:
        raise Problem(
            title="Not Authenticated",
            status_code=401,
            detail="authentication required",
        )

    org_id = requested_org_id or principal.org_id

    if not org_id:
        raise Problem(
            title="Organization Required",
            status_code=400,
            detail="X-Org-Id header required",
        )

    return await authz.resolve_context(
        principal,
        org_id=org_id,
    )


__all__ = [
    "configure_tenant_authorization",
    "get_membership_registry",
    "get_requested_org_id",
    "get_tenant_authorization",
    "require_org_id",
    "require_tenant_context",
]
