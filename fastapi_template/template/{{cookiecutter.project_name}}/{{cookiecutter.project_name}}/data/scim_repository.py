from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..core.scim import ScimUser

class ScimUserRepository(ABC):
    """
    Persistence contract used by the SCIM service.

    SQL and Mongo adapters implement this interface.
    """

    @abstractmethod
    async def create(
        self,
        *,
        user: ScimUser,
        org_id: str,
    ) -> ScimUser:
        ...

    @abstractmethod
    async def get(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> ScimUser | None:
        ...

    @abstractmethod
    async def get_by_external_id(
        self,
        *,
        external_id: str,
        org_id: str,
    ) -> ScimUser | None:
        ...

    @abstractmethod
    async def get_by_username(
        self,
        *,
        username: str,
        org_id: str,
    ) -> ScimUser | None:
        ...

    @abstractmethod
    async def replace(
        self,
        *,
        user_id: str,
        user: ScimUser,
        org_id: str,
        expected_version: int | None = None,
    ) -> ScimUser | None:
        ...

    @abstractmethod
    async def deactivate(
        self,
        *,
        user_id: str,
        org_id: str,
    ) -> bool:
        ...

    @abstractmethod
    async def list(
        self,
        *,
        org_id: str,
        filter_expression: Any | None,
        start_index: int,
        count: int,
    ) -> tuple[list[ScimUser], int]:
        ...

__all__ = ["ScimUserRepository"]
