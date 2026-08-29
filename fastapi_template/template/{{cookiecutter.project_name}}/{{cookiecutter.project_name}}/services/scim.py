from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..core.events import EventEnvelope
from ..core.scim import (
    ScimError,
    ScimListResponse,
    ScimPatchOperation,
    ScimUser,
)
from ..core.scim_patch import ScimPatchEngine
from ..data.scim_repository import ScimUserRepository

class ScimService:
    """
    Provider-neutral SCIM 2.0 user provisioning service.

    Responsible for:

    - identity resolution
    - duplicate protection
    - SCIM filtering
    - create
    - replace
    - PATCH
    - deactivation
    - pagination
    """

    def __init__(
        self,
        repository: ScimUserRepository,
        *,
        org_id: str,
        event_sink: Any | None = None,
    ) -> None:
        self.repository = repository
        self.org_id = org_id
        self.event_sink = event_sink

    async def create(self, user: ScimUser) -> ScimUser:
        existing = await self.repository.get_by_username(
            username=user.userName,
            org_id=self.org_id,
        )

        if existing is not None:
            raise ScimError(
                f"userName '{user.userName}' already exists",
                status_code=409,
                scim_type="uniqueness",
            )

        if user.externalId:
            existing = await self.repository.get_by_external_id(
                external_id=user.externalId,
                org_id=self.org_id,
            )

            if existing is not None:
                raise ScimError(
                    f"externalId '{user.externalId}' already exists",
                    status_code=409,
                    scim_type="uniqueness",
                )

        created = await self.repository.create(
            user=user,
            org_id=self.org_id,
        )

        await self._emit(
            "scim.user.created",
            created,
        )

        return self._decorate(created)

    async def get(self, user_id: str) -> ScimUser:
        user = await self.repository.get(
            user_id=user_id,
            org_id=self.org_id,
        )

        if user is None:
            raise ScimError(
                f"SCIM user '{user_id}' not found",
                status_code=404,
            )

        return self._decorate(user)

    async def replace(
        self,
        user_id: str,
        user: ScimUser,
    ) -> ScimUser:
        existing = await self.repository.get(
            user_id=user_id,
            org_id=self.org_id,
        )

        if existing is None:
            raise ScimError(
                f"SCIM user '{user_id}' not found",
                status_code=404,
            )

        if user.externalId:
            duplicate = await self.repository.get_by_external_id(
                external_id=user.externalId,
                org_id=self.org_id,
            )

            if duplicate and duplicate.id != user_id:
                raise ScimError(
                    "externalId already belongs to another user",
                    status_code=409,
                    scim_type="uniqueness",
                )

        updated = await self.repository.replace(
            user_id=user_id,
            user=user,
            org_id=self.org_id,
            expected_version=self._expected_version(existing),
        )

        if updated is None:
            raise ScimError(
                f"SCIM user '{user_id}' not found",
                status_code=404,
            )

        await self._emit(
            "scim.user.replaced",
            updated,
        )

        return self._decorate(updated)

    async def patch(
        self,
        user_id: str,
        operations: list[ScimPatchOperation],
    ) -> ScimUser:
        existing = await self.repository.get(
            user_id=user_id,
            org_id=self.org_id,
        )

        if existing is None:
            raise ScimError(
                f"SCIM user '{user_id}' not found",
                status_code=404,
            )

        patched = ScimPatchEngine.apply(
            existing,
            operations,
        )

        updated = await self.repository.replace(
            user_id=user_id,
            user=patched,
            org_id=self.org_id,
            expected_version=self._expected_version(existing),
        )

        if updated is None:
            raise ScimError(
                f"SCIM user '{user_id}' not found",
                status_code=404,
            )

        await self._emit(
            "scim.user.updated",
            updated,
        )

        return self._decorate(updated)

    async def delete(self, user_id: str) -> None:
        existing = await self.repository.get(
            user_id=user_id,
            org_id=self.org_id,
        )

        if existing is None:
            raise ScimError(
                f"SCIM user '{user_id}' not found",
                status_code=404,
            )

        # SCIM DELETE maps to deactivation in the platform.
        success = await self.repository.deactivate(
            user_id=user_id,
            org_id=self.org_id,
        )

        if not success:
            raise ScimError(
                f"SCIM user '{user_id}' could not be deactivated",
                status_code=404,
            )

        await self._emit(
            "scim.user.deactivated",
            existing,
        )

    async def list(
        self,
        *,
        filter_expression: Any | None,
        start_index: int = 1,
        count: int = 100,
    ) -> ScimListResponse:
        start_index = max(start_index, 1)
        count = max(0, min(count, 1000))

        users, total = await self.repository.list(
            org_id=self.org_id,
            filter_expression=filter_expression,
            start_index=start_index,
            count=count,
        )

        resources = [
            self._decorate(user)
            for user in users
        ]

        return ScimListResponse(
            totalResults=total,
            startIndex=start_index,
            itemsPerPage=len(resources),
            Resources=resources,
        )

    async def _emit(
        self,
        event_type: str,
        user: ScimUser,
    ) -> None:
        if self.event_sink is None:
            return

        envelope = EventEnvelope(
            type=event_type,
            source=f"/scim/Users/{user.id or ''}",
            data={
                "user_id": user.id,
                "external_id": user.externalId,
                "user_name": user.userName,
                "active": user.active,
                "org_id": self.org_id,
            },
        )

        await self.event_sink(envelope)


    @staticmethod
    def _expected_version(user: ScimUser) -> int | None:
        if user.meta is None or user.meta.version is None:
            return None
        try:
            return int(user.meta.version)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decorate(user: ScimUser) -> ScimUser:
        now = datetime.now(UTC).isoformat()

        if user.meta is None:
            from ..core.scim import ScimMeta

            user.meta = ScimMeta(
                resourceType="User",
                created=now,
                lastModified=now,
            )
        else:
            user.meta.lastModified = now

        return user

__all__ = ["ScimService"]
