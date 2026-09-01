"""Billing and entitlement interfaces independent of payment vendors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Entitlement:
    """A feature grant scoped to an organization."""

    org_id: str
    feature: str
    active: bool = True
    quantity: int | None = None


class BillingProvider(Protocol):
    async def create_checkout(self, *, org_id: str, price_id: str, return_url: str) -> str:
        """Create a hosted checkout URL."""

    async def sync_entitlements(self, *, org_id: str) -> list[Entitlement]:
        """Refresh grants from the billing provider."""


class InMemoryBillingProvider:
    """Local adapter that makes entitlement tests deterministic."""

    def __init__(self) -> None:
        self._entitlements: dict[str, list[Entitlement]] = {}

    def grant(self, entitlement: Entitlement) -> None:
        self._entitlements.setdefault(entitlement.org_id, []).append(entitlement)

    async def create_checkout(self, *, org_id: str, price_id: str, return_url: str) -> str:
        if not price_id or not return_url:
            raise ValueError("price_id and return_url are required")
        return f"{return_url}?org_id={org_id}&price_id={price_id}"

    async def sync_entitlements(self, *, org_id: str) -> list[Entitlement]:
        return list(self._entitlements.get(org_id, ()))


def require_entitlement(entitlements: list[Entitlement], feature: str) -> None:
    """Raise when an organization lacks an active feature grant."""
    if not any(item.feature == feature and item.active for item in entitlements):
        raise PermissionError(f"entitlement required: {feature}")


__all__ = [
    "BillingProvider",
    "Entitlement",
    "InMemoryBillingProvider",
    "require_entitlement",
]
