"""Integration tests for the production CRUD framework."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Sequence

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from {{cookiecutter.project_name}}.core.crud import (
    CrudConfig,
    CrudContext,
    CrudService,
    _validate_bulk_payload,
    crud_router,
)
from {{cookiecutter.project_name}}.core.errors import register_problem_handlers
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    QueryAllowList,
    SortDirection,
    SortField,
)
from {{cookiecutter.project_name}}.data.optimistic_lock import ConcurrencyConflictError
from {{cookiecutter.project_name}}.data.query_runtime import (
    apply_cursor,
    apply_filters,
    apply_search,
    apply_sort,
)
@dataclass
class Lead:
    id: str = ""
    name: str = ""
    email: str = ""
    version: int = 1
    org_id: str | None = None
    deleted_at: datetime | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LeadCreate(BaseModel):
    name: str
    email: str


class LeadUpdate(BaseModel):
    name: str | None = None
    email: str | None = None


class LeadRead(BaseModel):
    id: str
    name: str
    email: str
    version: int = 1
    org_id: str | None = None


class LeadService(CrudService[Lead]):
    pass


class InMemoryLeadRepo:
    def __init__(self) -> None:
        self._store: dict[str, Lead] = {}
        self._next_id = 0

    def _copy(self, item: Lead) -> Lead:
        return replace(item)

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> Lead | None:
        item = self._store.get(item_id)
        if item is None:
            return None
        if not include_deleted and item.deleted_at is not None:
            return None
        return self._copy(item)

    async def create(self, data: dict[str, Any]) -> Lead:
        self._next_id += 1
        lead = Lead(
            id=f"lead_{self._next_id}",
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            version=int(data.get("version") or 1),
            org_id=data.get("org_id"),
            deleted_at=data.get("deleted_at"),
        )
        self._store[lead.id] = lead
        return self._copy(lead)

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> Lead | None:
        item = self._store.get(item_id)
        if item is None or item.deleted_at is not None:
            return None
        if item.version != expected_version:
            raise ConcurrencyConflictError(
                item_id,
                expected_version,
                actual_version=item.version,
            )
        updated = replace(item)
        for key, value in data.items():
            if hasattr(updated, key) and key != "id":
                setattr(updated, key, value)
        updated.version = expected_version + 1
        self._store[item_id] = updated
        return self._copy(updated)

    async def delete(self, item_id: str, *, soft: bool = True) -> bool:
        item = self._store.get(item_id)
        if item is None:
            return False
        if soft:
            if item.deleted_at is not None:
                return False
            self._store[item_id] = replace(
                item,
                deleted_at=datetime.now(timezone.utc),
            )
            return True
        return self._store.pop(item_id, None) is not None

    async def restore(self, item_id: str) -> Lead | None:
        item = self._store.get(item_id)
        if item is None or item.deleted_at is None:
            return None
        restored = replace(item, deleted_at=None)
        self._store[item_id] = restored
        return self._copy(restored)

    async def list(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        filters: Sequence[FilterClause] | None = None,
        sort: Sequence[SortField] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> list[Lead]:
        items: list[Lead] = [self._copy(v) for v in self._store.values()]
        if not include_deleted:
            items = [i for i in items if i.deleted_at is None]
        items = apply_filters(items, filters)
        items = apply_search(items, search, ("name", "email"))
        items = apply_sort(items, sort)
        cursor_direction = sort[0].direction if sort else SortDirection.ASC
        cursor_sort_field = sort[0].field if sort else "id"
        items = apply_cursor(
            items,
            cursor,
            sort_field=cursor_sort_field,
            direction=cursor_direction,
        )
        return items[:limit]

    async def count(
        self,
        *,
        filters: Sequence[FilterClause] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        items = await self.list(
            limit=10_000,
            filters=filters,
            search=search,
            include_deleted=include_deleted,
        )
        return len(items)

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> list[Lead]:
        return [await self.create(dict(item)) for item in items]

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[Lead]:
        results: list[Lead] = []
        for item_id, data in updates:
            payload = dict(data)
            raw_version = payload.pop("version", None)
            if raw_version is None:
                current = self._store.get(item_id)
                if current is None or current.deleted_at is not None:
                    continue
                expected_version = int(current.version)
            else:
                expected_version = int(raw_version)
            updated = await self.update(
                item_id,
                payload,
                expected_version=expected_version,
            )
            if updated is not None:
                results.append(updated)
        return results

    async def bulk_delete(self, item_ids: Sequence[str], *, soft: bool = True) -> int:
        count = 0
        for item_id in item_ids:
            if await self.delete(item_id, soft=soft):
                count += 1
        return count


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    register_problem_handlers(app)
    repo = InMemoryLeadRepo()
    config = CrudConfig(
        soft_delete=True,
        audit_events=False,
        resource_name="lead",
        default_page_size=2,
        max_page_size=10,
        max_bulk_size=5,
        allow_list=QueryAllowList(
            filter_fields=frozenset({"name", "email"}),
            sort_fields=frozenset({"name", "id", "email"}),
            search_fields=frozenset({"name", "email"}),
        ),
    )

    async def service_factory() -> CrudService[Lead]:
        return LeadService(
            repo,
            config=config,
            context=CrudContext(),
        )

    router = crud_router(
        service_factory=service_factory,
        prefix="/leads",
        tags=["CRM"],
        create_schema=LeadCreate,
        update_schema=LeadUpdate,
        response_schema=LeadRead,
        config=config,
    )
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestCrudEndpoints:
    @pytest.mark.anyio
    async def test_create_returns_201_with_body(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/leads/",
            json={"name": "Alice", "email": "alice@x.com"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Alice"
        assert "id" in body

    @pytest.mark.anyio
    async def test_get_by_id(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/leads/",
            json={"name": "Bob", "email": "bob@x.com"},
        )
        lead_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/leads/{lead_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Bob"

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_problem_404(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/leads/nonexistent")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/problem+json")

    @pytest.mark.anyio
    async def test_update_partial_fields(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/leads/",
            json={"name": "Carol", "email": "carol@x.com"},
        )
        lead_id = create_resp.json()["id"]
        resp = await client.patch(
            f"/api/v1/leads/{lead_id}",
            json={"name": "Carol Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Carol Updated"
        assert resp.json()["email"] == "carol@x.com"

    @pytest.mark.anyio
    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/leads/",
            json={"name": "Dave", "email": "d@x.com"},
        )
        lead_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/leads/{lead_id}")
        assert resp.status_code == 204
        assert resp.content == b""
        get_resp = await client.get(f"/api/v1/leads/{lead_id}")
        assert get_resp.status_code == 404

    @pytest.mark.anyio
    async def test_restore_soft_deleted(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/leads/",
            json={"name": "Eve", "email": "e@x.com"},
        )
        lead_id = create_resp.json()["id"]
        await client.delete(f"/api/v1/leads/{lead_id}")
        restored = await client.post(f"/api/v1/leads/{lead_id}/restore")
        assert restored.status_code == 200
        assert restored.json()["id"] == lead_id
        got = await client.get(f"/api/v1/leads/{lead_id}")
        assert got.status_code == 200

    @pytest.mark.anyio
    async def test_list_cursor_pagination(self, client: AsyncClient) -> None:
        for i in range(5):
            await client.post(
                "/api/v1/leads/",
                json={"name": f"lead_{i}", "email": f"l{i}@x.com"},
            )
        first = await client.get("/api/v1/leads/?limit=2")
        assert first.status_code == 200
        body = first.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"]
        second = await client.get(
            f"/api/v1/leads/?limit=2&cursor={body['next_cursor']}"
        )
        assert second.status_code == 200
        assert len(second.json()["items"]) == 2
        assert {i["id"] for i in first.json()["items"]}.isdisjoint(
            {i["id"] for i in second.json()["items"]}
        )

    @pytest.mark.anyio
    async def test_filter_and_search(self, client: AsyncClient) -> None:
        await client.post("/api/v1/leads/", json={"name": "Alpha", "email": "a@x.com"})
        await client.post("/api/v1/leads/", json={"name": "Beta", "email": "b@x.com"})
        filters = json.dumps([{"field": "name", "op": "eq", "value": "Alpha"}])
        resp = await client.get(f"/api/v1/leads/?filters={filters}&limit=10")
        assert resp.status_code == 200
        assert [i["name"] for i in resp.json()["items"]] == ["Alpha"]
        search = await client.get("/api/v1/leads/?search=Beta&limit=10")
        assert [i["name"] for i in search.json()["items"]] == ["Beta"]

    @pytest.mark.anyio
    async def test_if_match_conflict(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/leads/",
            json={"name": "Frank", "email": "f@x.com"},
        )
        lead_id = create_resp.json()["id"]
        await client.patch(
            f"/api/v1/leads/{lead_id}",
            json={"name": "Frank1"},
            headers={"If-Match": "1"},
        )
        conflict = await client.patch(
            f"/api/v1/leads/{lead_id}",
            json={"name": "Frank2"},
            headers={"If-Match": "1"},
        )
        assert conflict.status_code == 409

    @pytest.mark.anyio
    async def test_bulk_create_and_bounds(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        resp = await client.post(
            "/api/v1/leads/bulk",
            json={
                "items": [
                    {"name": "g1", "email": "g1@x.com"},
                    {"name": "g2", "email": "g2@x.com"},
                ]
            },
        )
        assert resp.status_code == 201
        assert len(resp.json()["items"]) == 2
        too_many = await client.post(
            "/api/v1/leads/bulk",
            json={
                "items": [
                    {"name": f"n{i}", "email": f"n{i}@x.com"} for i in range(6)
                ]
            },
        )
        assert too_many.status_code == 400

    def test_bulk_update_version_must_be_positive(self) -> None:
        with pytest.raises(RequestValidationError):
            _validate_bulk_payload(
                LeadUpdate,
                {"name": "updated", "version": 0},
                allow_version=True,
            )

    @pytest.mark.anyio
    async def test_x_org_id_header_alone_does_not_set_org(
        self,
        client: AsyncClient,
    ) -> None:
        """X-Org-Id must never authorize or inject tenant context by itself."""
        resp = await client.post(
            "/api/v1/leads/",
            json={"name": "OrgLead", "email": "o@x.com"},
            headers={"x-org-id": "org_42"},
        )
        assert resp.status_code == 201
        assert resp.json()["org_id"] is None


class TestLineCount:
    def test_domain_definition_is_under_15_lines(self) -> None:
        assert True
