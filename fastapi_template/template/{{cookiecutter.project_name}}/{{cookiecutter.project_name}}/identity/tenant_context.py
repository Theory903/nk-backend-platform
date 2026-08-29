"""
Tenant-scoped authorization boundary.

Authorization flow:

    Principal
        |
        v
    MembershipResolver
        |
        v
    TenantContext
        |
        +--> permission check
        |
        +--> resource ownership check
        |
        v
    Repository / database
        |
        v
    PostgreSQL RLS

Application code must resolve a TenantContext before accessing
tenant-owned resources.

Important:
    Application-level authorization is not the final isolation boundary.
    PostgreSQL RLS should remain the defense-in-depth enforcement layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.identity.permissions import has_permission
from {{cookiecutter.project_name}}.identity.principal import Principal


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Membership:
    """
    User membership in an organization.

    A membership is immutable from the caller's perspective.
    Changes should be represented by replacing the persisted membership.
    """

    user_id: str
    org_id: str
    roles: frozenset[str] = frozenset()
    active: bool = True


class MembershipResolver(Protocol):
    """
    Persistence-independent membership lookup.

    Production implementation should query the database.
    """

    async def get_membership(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> Membership | None:
        ...


# ---------------------------------------------------------------------------
# Tenant context
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TenantContext:
    """
    Authenticated principal operating inside one organization.

    This is the authorization context passed to application services.
    """

    principal: Principal
    org_id: str
    roles: frozenset[str]

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def is_service(self) -> bool:
        return self.principal.is_service

    @property
    def is_active(self) -> bool:
        return (
            bool(self.org_id)
            and not self.principal.is_anonymous
            and bool(self.roles)
        )

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))

    def has_permission(self, permission: str) -> bool:
        """
        Check a permission against the roles resolved for this tenant.

        Scopes the principal to this org/roles while preserving
        ``is_service`` and ``provider``.
        """
        scoped_principal = (
            self.principal
            .with_org(self.org_id)
            .with_roles(self.roles)
        )

        return has_permission(
            scoped_principal,
            permission,
        )

    def require(
        self,
        permission: str,
    ) -> None:
        """
        Require an active tenant context and permission.
        """
        if not self.is_active:
            raise Problem(
                title="No Active Organization",
                status_code=403,
                detail=(
                    "principal has no active organization "
                    "membership"
                ),
            )

        if not self.has_permission(permission):
            raise Problem(
                title="Insufficient Permissions",
                status_code=403,
                detail=(
                    f"requires '{permission}' "
                    f"in org '{self.org_id}'"
                ),
            )


# ---------------------------------------------------------------------------
# Resource ownership
# ---------------------------------------------------------------------------


class ResourceOwnershipResolver(Protocol):
    """
    Resolves the organization that owns a resource.

    Production implementations should query the resource repository/database.
    """

    async def get_resource_org(
        self,
        resource_key: str,
    ) -> str | None:
        ...


# ---------------------------------------------------------------------------
# Tenant authorization service
# ---------------------------------------------------------------------------


class TenantAuthorizationService:
    """
    Central tenant authorization boundary.

    Responsibilities:

    1. Verify principal membership.
    2. Resolve tenant roles.
    3. Construct TenantContext.
    4. Verify resource ownership.
    5. Verify permission.

    This class does not replace PostgreSQL RLS.
    RLS remains the final tenant-isolation mechanism.
    """

    def __init__(
        self,
        memberships: MembershipResolver,
        resources: ResourceOwnershipResolver,
    ) -> None:
        self._memberships = memberships
        self._resources = resources

    async def resolve_context(
        self,
        principal: Principal,
        *,
        org_id: str,
    ) -> TenantContext:
        """
        Resolve an authenticated principal into a tenant context.
        """
        if principal.is_anonymous:
            raise Problem(
                title="Not Authenticated",
                status_code=401,
                detail="anonymous principals cannot access organizations",
            )

        if not org_id:
            raise Problem(
                title="Organization Required",
                status_code=400,
                detail="org_id is required",
            )

        membership = await self._memberships.get_membership(
            user_id=principal.user_id,
            org_id=org_id,
        )

        if membership is None or not membership.active:
            raise Problem(
                title="Not A Member",
                status_code=403,
                detail=(
                    f"user '{principal.user_id}' is not "
                    f"an active member of org '{org_id}'"
                ),
            )

        if membership.user_id != principal.user_id:
            raise Problem(
                title="Membership Mismatch",
                status_code=403,
                detail="membership does not belong to the authenticated principal",
            )

        return TenantContext(
            principal=principal,
            org_id=membership.org_id,
            roles=membership.roles,
        )

    async def authorize_resource(
        self,
        ctx: TenantContext,
        *,
        resource_key: str,
        permission: str,
    ) -> None:
        """
        Verify:

            principal -> tenant -> resource -> permission
        """
        if not ctx.is_active:
            raise Problem(
                title="No Active Organization",
                status_code=403,
                detail="tenant context is not active",
            )

        resource_org = await self._resources.get_resource_org(
            resource_key
        )

        if resource_org is None:
            raise Problem(
                title="Resource Not Found",
                status_code=404,
                detail=resource_key,
            )

        if resource_org != ctx.org_id:
            raise Problem(
                title="Cross-Tenant Access Denied",
                status_code=403,
                detail="resource does not belong to the active organization",
            )

        ctx.require(permission)


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryMembershipRegistry:
    """
    Development/test membership resolver.

    Do not use as the production source of truth.
    """

    def __init__(self) -> None:
        self._memberships: dict[
            tuple[str, str],
            Membership,
        ] = {}

    async def get_membership(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> Membership | None:
        return self._memberships.get(
            (user_id, org_id)
        )

    def add_membership(
        self,
        *,
        user_id: str,
        org_id: str,
        roles: frozenset[str],
    ) -> Membership:
        if not user_id:
            raise ValueError(
                "user_id is required"
            )

        if not org_id:
            raise ValueError(
                "org_id is required"
            )

        membership = Membership(
            user_id=user_id,
            org_id=org_id,
            roles=roles,
            active=True,
        )

        self._memberships[
            (user_id, org_id)
        ] = membership

        return membership

    def update_roles(
        self,
        *,
        user_id: str,
        org_id: str,
        roles: frozenset[str],
    ) -> Membership | None:
        current = self._memberships.get(
            (user_id, org_id)
        )

        if current is None:
            return None

        updated = Membership(
            user_id=current.user_id,
            org_id=current.org_id,
            roles=roles,
            active=current.active,
        )

        self._memberships[
            (user_id, org_id)
        ] = updated

        return updated

    def activate(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> bool:
        current = self._memberships.get(
            (user_id, org_id)
        )

        if current is None:
            return False

        self._memberships[
            (user_id, org_id)
        ] = Membership(
            user_id=current.user_id,
            org_id=current.org_id,
            roles=current.roles,
            active=True,
        )

        return True

    def deactivate(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> bool:
        current = self._memberships.get(
            (user_id, org_id)
        )

        if current is None:
            return False

        self._memberships[
            (user_id, org_id)
        ] = Membership(
            user_id=current.user_id,
            org_id=current.org_id,
            roles=current.roles,
            active=False,
        )

        return True

    def remove_membership(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> bool:
        return (
            self._memberships.pop(
                (user_id, org_id),
                None,
            )
            is not None
        )

    def list_for_user(
        self,
        user_id: str,
    ) -> list[Membership]:
        return [
            membership
            for membership in self._memberships.values()
            if (
                membership.user_id == user_id
                and membership.active
            )
        ]

    def list_for_org(
        self,
        org_id: str,
    ) -> list[Membership]:
        return [
            membership
            for membership in self._memberships.values()
            if (
                membership.org_id == org_id
                and membership.active
            )
        ]

    def revoke_org(
        self,
        org_id: str,
    ) -> int:
        """
        Deactivate every membership in an organization.
        """
        affected = 0

        for key, membership in list(
            self._memberships.items()
        ):
            if (
                membership.org_id == org_id
                and membership.active
            ):
                self._memberships[key] = Membership(
                    user_id=membership.user_id,
                    org_id=membership.org_id,
                    roles=membership.roles,
                    active=False,
                )

                affected += 1

        return affected


class InMemoryResourceOwnershipRegistry:
    """
    Development/test resource ownership resolver.
    """

    def __init__(self) -> None:
        self._resources: dict[str, str] = {}

    async def get_resource_org(
        self,
        resource_key: str,
    ) -> str | None:
        return self._resources.get(
            resource_key
        )

    def register(
        self,
        *,
        resource_key: str,
        org_id: str,
    ) -> None:
        if not resource_key:
            raise ValueError(
                "resource_key is required"
            )

        if not org_id:
            raise ValueError(
                "org_id is required"
            )

        self._resources[
            resource_key
        ] = org_id

    def unregister(
        self,
        resource_key: str,
    ) -> bool:
        return (
            self._resources.pop(
                resource_key,
                None,
            )
            is not None
        )


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


def create_tenant_authorization(
    memberships: MembershipResolver,
    resources: ResourceOwnershipResolver,
) -> TenantAuthorizationService:
    """
    Build the tenant authorization boundary.
    """
    return TenantAuthorizationService(
        memberships=memberships,
        resources=resources,
    )


__all__ = [
    "Membership",
    "MembershipResolver",
    "TenantContext",
    "ResourceOwnershipResolver",
    "TenantAuthorizationService",
    "InMemoryMembershipRegistry",
    "InMemoryResourceOwnershipRegistry",
    "create_tenant_authorization",
]