from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class KycStatus(StrEnum):
    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class KycProvider(Protocol):
    async def get_status(self, org_id: str) -> KycStatus: ...


class InMemoryKycProvider:
    def __init__(self) -> None:
        self._status: dict[str, KycStatus] = {}

    def set_status(self, org_id: str, status: KycStatus) -> None:
        self._status[org_id] = status

    async def get_status(self, org_id: str) -> KycStatus:
        return self._status.get(org_id, KycStatus.unverified)


class KycGateError(ValueError):
    pass


async def assert_kyc_allows(
    provider: KycProvider,
    org_id: str,
    amount_minor: int,
    threshold_minor: int = 1_000_00,
) -> None:
    if amount_minor > threshold_minor:
        status = await provider.get_status(org_id)
        if status != KycStatus.verified:
            raise KycGateError(f"kyc {status} blocks transaction above {threshold_minor}")
