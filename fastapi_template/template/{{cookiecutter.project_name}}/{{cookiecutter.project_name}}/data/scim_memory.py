"""In-memory SCIM repository for local development and tests."""

from __future__ import annotations

from typing import Any

from {{cookiecutter.project_name}}.core.scim import ScimMeta, ScimUser
from {{cookiecutter.project_name}}.core.scim_filter import (
    FilterExpression,
    FilterGroup,
    FilterOperator,
)
from {{cookiecutter.project_name}}.data.scim_repository import ScimUserRepository


class InMemoryScimRepository(ScimUserRepository):
    """Org-scoped in-memory SCIM store."""

    def __init__(self) -> None:
        self._users: dict[str, dict[str, ScimUser]] = {}
        self._versions: dict[str, dict[str, int]] = {}
        self._seq = 0

    def _org(self, org_id: str) -> dict[str, ScimUser]:
        return self._users.setdefault(org_id, {})

    def _org_versions(self, org_id: str) -> dict[str, int]:
        return self._versions.setdefault(org_id, {})

    async def create(self, *, user: ScimUser, org_id: str) -> ScimUser:
        self._seq += 1
        user_id = user.id or f"scim_{self._seq}"
        created = user.model_copy(deep=True)
        created.id = user_id
        created.meta = ScimMeta(resourceType="User", version="1")
        self._org(org_id)[user_id] = created
        self._org_versions(org_id)[user_id] = 1
        return created.model_copy(deep=True)

    async def get(self, *, user_id: str, org_id: str) -> ScimUser | None:
        user = self._org(org_id).get(user_id)
        return user.model_copy(deep=True) if user else None

    async def get_by_external_id(
        self,
        *,
        external_id: str,
        org_id: str,
    ) -> ScimUser | None:
        for user in self._org(org_id).values():
            if user.externalId == external_id:
                return user.model_copy(deep=True)
        return None

    async def get_by_username(
        self,
        *,
        username: str,
        org_id: str,
    ) -> ScimUser | None:
        for user in self._org(org_id).values():
            if user.userName == username:
                return user.model_copy(deep=True)
        return None

    async def replace(
        self,
        *,
        user_id: str,
        user: ScimUser,
        org_id: str,
        expected_version: int | None = None,
    ) -> ScimUser | None:
        existing = self._org(org_id).get(user_id)
        if existing is None:
            return None

        version = self._org_versions(org_id)[user_id]
        if expected_version is not None and version != expected_version:
            from {{cookiecutter.project_name}}.data.optimistic_lock import (
                ConcurrencyConflictError,
            )

            raise ConcurrencyConflictError(
                user_id,
                expected_version,
                version,
            )

        updated = user.model_copy(deep=True)
        updated.id = user_id
        version += 1
        self._org_versions(org_id)[user_id] = version
        updated.meta = ScimMeta(resourceType="User", version=str(version))
        self._org(org_id)[user_id] = updated
        return updated.model_copy(deep=True)

    async def deactivate(self, *, user_id: str, org_id: str) -> bool:
        existing = self._org(org_id).get(user_id)
        if existing is None:
            return False
        existing.active = False
        version = self._org_versions(org_id)[user_id] + 1
        self._org_versions(org_id)[user_id] = version
        existing.meta = ScimMeta(resourceType="User", version=str(version))
        return True

    async def list(
        self,
        *,
        org_id: str,
        filter_expression: Any | None,
        start_index: int,
        count: int,
    ) -> tuple[list[ScimUser], int]:
        users = list(self._org(org_id).values())
        if filter_expression is not None:
            users = [
                user
                for user in users
                if self._matches(user, filter_expression)
            ]

        total = len(users)
        offset = max(start_index - 1, 0)
        page = users[offset : offset + count]
        return [user.model_copy(deep=True) for user in page], total

    def _matches(self, user: ScimUser, expression: Any) -> bool:
        if isinstance(expression, FilterGroup):
            results = [self._matches(user, child) for child in expression.children]
            if expression.operator == "and":
                return all(results)
            return any(results)

        if not isinstance(expression, FilterExpression):
            return True

        value = self._attr(user, expression.attribute)
        op = expression.operator

        if op is FilterOperator.PR:
            return value is not None and value != ""

        if op is FilterOperator.EQ:
            return value == expression.value

        if op is FilterOperator.CO:
            return isinstance(value, str) and str(expression.value) in value

        if op is FilterOperator.SW:
            return isinstance(value, str) and value.startswith(str(expression.value))

        return True

    @staticmethod
    def _attr(user: ScimUser, name: str) -> Any:
        mapping = {
            "userName": user.userName,
            "externalId": user.externalId,
            "active": user.active,
            "displayName": user.displayName,
        }
        return mapping.get(name)


__all__ = ["InMemoryScimRepository"]
