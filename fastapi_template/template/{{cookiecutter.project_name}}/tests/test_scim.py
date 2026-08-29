"""Focused SCIM 2.0 unit tests (filter, patch, service)."""

from __future__ import annotations

from typing import Any

import pytest

from {{cookiecutter.project_name}}.core.scim import (
    ScimEmail,
    ScimError,
    ScimMeta,
    ScimName,
    ScimPatchOperation,
    ScimUser,
)
from {{cookiecutter.project_name}}.core.scim_filter import (
    FilterExpression,
    FilterGroup,
    FilterOperator,
    ScimFilterError,
    ScimFilterParser,
)
from {{cookiecutter.project_name}}.core.scim_patch import ScimPatchEngine
from {{cookiecutter.project_name}}.data.scim_repository import ScimUserRepository
from {{cookiecutter.project_name}}.services.scim import ScimService


class InMemoryScimRepository(ScimUserRepository):
    """Simple org-scoped in-memory SCIM store for service tests."""

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
            results = [
                self._matches(user, child)
                for child in expression.children
            ]
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
            return isinstance(value, str) and value.startswith(
                str(expression.value),
            )

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


# --- Filter parser ---


def test_filter_eq() -> None:
    parsed = ScimFilterParser('userName eq "john@example.com"').parse()
    assert isinstance(parsed, FilterExpression)
    assert parsed.attribute == "userName"
    assert parsed.operator is FilterOperator.EQ
    assert parsed.value == "john@example.com"


def test_filter_and_or() -> None:
    parsed = ScimFilterParser(
        'userName eq "john" and active eq true',
    ).parse()
    assert isinstance(parsed, FilterGroup)
    assert parsed.operator == "and"
    assert len(parsed.children) == 2

    parsed_or = ScimFilterParser(
        'userName eq "a" or userName eq "b"',
    ).parse()
    assert isinstance(parsed_or, FilterGroup)
    assert parsed_or.operator == "or"


def test_filter_co_sw_pr() -> None:
    co = ScimFilterParser('userName co "john"').parse()
    assert isinstance(co, FilterExpression)
    assert co.operator is FilterOperator.CO

    sw = ScimFilterParser('userName sw "john"').parse()
    assert isinstance(sw, FilterExpression)
    assert sw.operator is FilterOperator.SW

    pr = ScimFilterParser("externalId pr").parse()
    assert isinstance(pr, FilterExpression)
    assert pr.operator is FilterOperator.PR
    assert pr.value is None


def test_filter_invalid() -> None:
    with pytest.raises(ScimFilterError):
        ScimFilterParser("userName xxx true").parse()

    with pytest.raises(ScimFilterError):
        ScimFilterParser("").parse()


# --- Patch engine ---


def _sample_user() -> ScimUser:
    return ScimUser(
        userName="john.doe",
        active=True,
        displayName="John Doe",
        name=ScimName(givenName="John", familyName="Doe"),
        emails=[
            ScimEmail(value="john@example.com", primary=True),
        ],
        meta=ScimMeta(resourceType="User", version="1"),
    )


def test_patch_replace_active_and_given_name() -> None:
    patched = ScimPatchEngine.apply(
        _sample_user(),
        [
            ScimPatchOperation(op="replace", path="active", value=False),
            ScimPatchOperation(
                op="replace",
                path="name.givenName",
                value="Jon",
            ),
        ],
    )
    assert patched.active is False
    assert patched.name is not None
    assert patched.name.givenName == "Jon"
    assert patched.name.familyName == "Doe"


def test_patch_remove_emails() -> None:
    patched = ScimPatchEngine.apply(
        _sample_user(),
        [ScimPatchOperation(op="remove", path="emails")],
    )
    assert patched.emails == []


def test_patch_invalid_path() -> None:
    with pytest.raises(ScimError) as exc:
        ScimPatchEngine.apply(
            _sample_user(),
            [ScimPatchOperation(op="replace", path="password", value="x")],
        )
    assert exc.value.scim_type == "invalidPath"


# --- ScimService ---


@pytest.fixture
def service() -> ScimService:
    return ScimService(
        InMemoryScimRepository(),
        org_id="org_test",
    )


@pytest.mark.anyio
async def test_service_create_uniqueness(service: ScimService) -> None:
    user = ScimUser(
        userName="alice",
        emails=[ScimEmail(value="a@b.c", primary=True)],
    )
    created = await service.create(user)
    assert created.id is not None
    assert created.active is True

    with pytest.raises(ScimError) as exc:
        await service.create(
            ScimUser(userName="alice"),
        )
    assert exc.value.status_code == 409
    assert exc.value.scim_type == "uniqueness"


@pytest.mark.anyio
async def test_service_get_404(service: ScimService) -> None:
    with pytest.raises(ScimError) as exc:
        await service.get("missing")
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_service_patch_and_delete_deactivates(
    service: ScimService,
) -> None:
    created = await service.create(
        ScimUser(
            userName="bob",
            name=ScimName(givenName="Bob"),
            emails=[ScimEmail(value="bob@x.com", primary=True)],
        ),
    )
    assert created.id is not None

    patched = await service.patch(
        created.id,
        [
            ScimPatchOperation(
                op="replace",
                path="name.givenName",
                value="Robert",
            ),
        ],
    )
    assert patched.name is not None
    assert patched.name.givenName == "Robert"

    await service.delete(created.id)
    deactivated = await service.get(created.id)
    assert deactivated.active is False


@pytest.mark.anyio
async def test_service_list_pagination(service: ScimService) -> None:
    for index in range(5):
        await service.create(ScimUser(userName=f"user{index}"))

    page = await service.list(
        filter_expression=None,
        start_index=2,
        count=2,
    )
    assert page.totalResults == 5
    assert page.startIndex == 2
    assert page.itemsPerPage == 2
    assert len(page.Resources) == 2
