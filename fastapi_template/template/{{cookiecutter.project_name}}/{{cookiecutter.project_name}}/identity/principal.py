"""Authenticated principal used across authentication and authorization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Principal:
    """
    Authenticated actor.

    A Principal represents the identity that reached the application after
    authentication. Authorization layers use its identity, organization,
    roles, provider, and service-account status.

    Authentication status is represented by user_id:
        user_id=""  -> anonymous
        user_id!= "" -> authenticated

    Tenant authorization is separate from role authorization.
    Permission catalogs live outside this type — do not add permission
    fields here.
    """

    user_id: str
    org_id: str | None = None
    roles: frozenset[str] = frozenset()
    provider: str = "local"
    is_service: bool = False

    def __post_init__(self) -> None:
        """
        Normalize values at construction time.

        Frozen dataclasses can still normalize fields through
        object.__setattr__ during initialization.
        """

        object.__setattr__(
            self,
            "user_id",
            self.user_id.strip(),
        )

        if self.org_id is not None:
            normalized_org = self.org_id.strip()

            object.__setattr__(
                self,
                "org_id",
                normalized_org or None,
            )

        normalized_roles = frozenset(
            role.strip()
            for role in self.roles
            if role and role.strip()
        )

        object.__setattr__(
            self,
            "roles",
            normalized_roles,
        )

        object.__setattr__(
            self,
            "provider",
            self.provider.strip() or "local",
        )

    @property
    def is_anonymous(self) -> bool:
        """Whether this principal represents an unauthenticated actor."""

        return not bool(self.user_id)

    @property
    def is_authenticated(self) -> bool:
        """Whether authentication produced a concrete identity."""

        return bool(self.user_id)

    @property
    def is_tenant_scoped(self) -> bool:
        """Whether the principal has an organization scope."""

        return self.org_id is not None

    def has_role(
        self,
        role: str,
    ) -> bool:
        """Return whether the principal has a specific role."""

        return role in self.roles

    def has_any_role(
        self,
        *roles: str,
    ) -> bool:
        """Return whether the principal has at least one requested role."""

        return bool(
            self.roles.intersection(roles)
        )

    def has_all_roles(
        self,
        *roles: str,
    ) -> bool:
        """Return whether the principal has every requested role."""

        return set(roles).issubset(self.roles)

    def require_org(self) -> str:
        """
        Return the organization ID or raise if the principal is not
        tenant-scoped.
        """

        if self.org_id is None:
            raise ValueError(
                "principal has no organization scope"
            )

        return self.org_id

    def with_roles(
        self,
        roles: Iterable[str],
    ) -> Principal:
        """Return a new principal with a replacement role set."""

        return Principal(
            user_id=self.user_id,
            org_id=self.org_id,
            roles=frozenset(roles),
            provider=self.provider,
            is_service=self.is_service,
        )

    def with_org(
        self,
        org_id: str | None,
    ) -> Principal:
        """Return a new principal with a replacement organization scope."""

        return Principal(
            user_id=self.user_id,
            org_id=org_id,
            roles=self.roles,
            provider=self.provider,
            is_service=self.is_service,
        )


Anonymous = Principal(user_id="")

__all__ = [
    "Anonymous",
    "Principal",
]
