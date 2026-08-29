"""First-class machine identities.

Service accounts represent workers, agents, integrations, and microservices.
They are distinct from human users and always belong to an organization.

A service account is an *identity*, not a credential. API keys, OAuth client
secrets, and workload identities authenticate *as* the account and must be
managed by those layers. Deactivating a service account in this registry does
**not** revoke credentials by itself — the higher cascade / auth boundary must
revoke API keys (and related secrets) keyed by ``account_id``.

Principals for machine auth should use the immutable ``account_id``, never the
mutable display ``name``.
"""

from __future__ import annotations

import ipaddress
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "ServiceAccount",
    "ServiceAccountRegistry",
]


@dataclass
class ServiceAccount:
    """Machine identity owned by an organization."""

    account_id: str
    name: str
    org_id: str

    roles: frozenset[str] = field(
        default_factory=lambda: frozenset({"service"})
    )

    allowed_ips: tuple[str, ...] = ()

    active: bool = True

    created_by: str = ""

    description: str = ""

    created_at: float = field(
        default_factory=time.time
    )

    deactivated_at: float | None = None

    metadata: dict[str, str] = field(
        default_factory=dict
    )

    @property
    def principal_type(self) -> str:
        return "service_account"

    @property
    def is_active(self) -> bool:
        return self.active and self.deactivated_at is None

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def allows_ip(self, client_ip: str | None) -> bool:
        """
        Check client IP against the configured allowlist.

        Entries may be individual addresses or CIDR networks.

        Empty allowlist means unrestricted network access.
        """
        if not self.allowed_ips:
            return True

        if not client_ip:
            return False

        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False

        for entry in self.allowed_ips:
            try:
                network = ipaddress.ip_network(
                    entry,
                    strict=False,
                )
            except ValueError:
                continue

            if address in network:
                return True

        return False


class ServiceAccountRegistry:
    """
    Registry for machine identities.

    Development implementation uses memory.

    Production should back this with the platform repository and enforce
    org-scoped uniqueness at the database level.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, ServiceAccount] = {}

        # (org_id, normalized_name) -> account_id
        self._by_name: dict[tuple[str, str], str] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.strip().lower().split())

    def create(
        self,
        name: str,
        org_id: str,
        *,
        roles: Iterable[str] | None = None,
        allowed_ips: Iterable[str] | None = None,
        created_by: str = "",
        description: str = "",
        metadata: dict[str, str] | None = None,
    ) -> ServiceAccount:
        name = name.strip()
        org_id = org_id.strip()

        if not name:
            raise ValueError(
                "service account name is required"
            )

        if not org_id:
            raise ValueError(
                "org_id is required"
            )

        normalized_name = self._normalize_name(name)
        name_key = (org_id, normalized_name)

        if name_key in self._by_name:
            raise ValueError(
                f"service account '{name}' already exists"
            )

        normalized_ips = self._normalize_ips(
            allowed_ips or ()
        )

        effective_roles = frozenset(
            roles or {"service"}
        )

        if not effective_roles:
            effective_roles = frozenset({"service"})

        if "service" not in effective_roles:
            effective_roles = effective_roles | {"service"}

        account = ServiceAccount(
            account_id=f"sa_{uuid.uuid4().hex}",
            name=name,
            org_id=org_id,
            roles=effective_roles,
            allowed_ips=normalized_ips,
            created_by=created_by,
            description=description,
            metadata=dict(metadata or {}),
        )

        self._accounts[account.account_id] = account
        self._by_name[name_key] = account.account_id

        return account

    @staticmethod
    def _normalize_ips(
        values: Iterable[str],
    ) -> tuple[str, ...]:
        result: list[str] = []

        for value in values:
            value = value.strip()

            if not value:
                continue

            try:
                # Accept both individual IPs and CIDR.
                if "/" in value:
                    network = ipaddress.ip_network(
                        value,
                        strict=False,
                    )
                    normalized = str(network)
                else:
                    normalized = str(
                        ipaddress.ip_address(value)
                    )
            except ValueError as exc:
                raise ValueError(
                    f"invalid IP/CIDR: {value}"
                ) from exc

            if normalized not in result:
                result.append(normalized)

        return tuple(result)

    def get(
        self,
        account_id: str,
        *,
        include_inactive: bool = False,
        org_id: str | None = None,
    ) -> ServiceAccount | None:
        account = self._accounts.get(account_id)

        if account is None:
            return None

        if org_id is not None and account.org_id != org_id:
            return None

        if not include_inactive and not account.is_active:
            return None

        return account

    def get_active(
        self,
        account_id: str,
        *,
        org_id: str | None = None,
        client_ip: str | None = None,
    ) -> ServiceAccount | None:
        """
        Authentication-facing lookup.

        Requires:
        - account exists
        - account is active
        - tenant matches
        - source IP is allowed
        """
        account = self.get(
            account_id,
            org_id=org_id,
        )

        if account is None:
            return None

        if not account.allows_ip(client_ip):
            return None

        return account

    def get_by_name(
        self,
        org_id: str,
        name: str,
        *,
        include_inactive: bool = False,
    ) -> ServiceAccount | None:
        normalized_name = self._normalize_name(name)

        account_id = self._by_name.get(
            (org_id, normalized_name)
        )

        if account_id is None:
            return None

        return self.get(
            account_id,
            include_inactive=include_inactive,
            org_id=org_id,
        )

    def deactivate(
        self,
        account_id: str,
        *,
        org_id: str | None = None,
    ) -> bool:
        account = self._accounts.get(account_id)

        if account is None:
            return False

        if org_id is not None and account.org_id != org_id:
            return False

        if not account.is_active:
            return False

        account.active = False
        account.deactivated_at = time.time()

        return True

    def activate(
        self,
        account_id: str,
        *,
        org_id: str | None = None,
    ) -> bool:
        account = self._accounts.get(account_id)

        if account is None:
            return False

        if org_id is not None and account.org_id != org_id:
            return False

        if account.deactivated_at is None:
            return False

        account.active = True
        account.deactivated_at = None

        return True

    def delete(
        self,
        account_id: str,
        *,
        org_id: str | None = None,
    ) -> bool:
        """
        Remove registry record.

        Prefer deactivation for normal lifecycle operations.
        """
        account = self._accounts.get(account_id)

        if account is None:
            return False

        if org_id is not None and account.org_id != org_id:
            return False

        self._accounts.pop(account_id, None)

        name_key = (
            account.org_id,
            self._normalize_name(account.name),
        )

        self._by_name.pop(name_key, None)

        return True

    def list_for_org(
        self,
        org_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[ServiceAccount]:
        accounts = [
            account
            for account in self._accounts.values()
            if account.org_id == org_id
        ]

        if not include_inactive:
            accounts = [
                account
                for account in accounts
                if account.is_active
            ]

        accounts.sort(
            key=lambda account: (
                account.created_at,
                account.account_id,
            )
        )

        return accounts

    def list_created_by(
        self,
        owner_id: str,
        *,
        org_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[ServiceAccount]:
        accounts = [
            account
            for account in self._accounts.values()
            if account.created_by == owner_id
        ]

        if org_id is not None:
            accounts = [
                account
                for account in accounts
                if account.org_id == org_id
            ]

        if not include_inactive:
            accounts = [
                account
                for account in accounts
                if account.is_active
            ]

        return accounts

    def deactivate_created_by(
        self,
        owner_id: str,
        *,
        org_id: str | None = None,
    ) -> int:
        """
        Deactivate every service account created by a user.

        Used by account suspension/deactivation cascades.
        """
        count = 0

        for account in self._accounts.values():
            if account.created_by != owner_id:
                continue

            if org_id is not None and account.org_id != org_id:
                continue

            if not account.is_active:
                continue

            account.active = False
            account.deactivated_at = time.time()

            count += 1

        return count