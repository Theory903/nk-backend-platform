"""Production generic CRUD service and router factory.

Business modules subclass CrudService and override lifecycle hooks.
`crud_router` generates thin HTTP endpoints; the service owns
authorization, audit, query validation, and domain errors.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.logging import get_logger
from {{cookiecutter.project_name}}.core.pagination import make_cursor, parse_cursor
from {{cookiecutter.project_name}}.core.query import (
    FilterClause,
    FilterOp,
    QueryAllowList,
    QuerySpec,
    SortDirection,
    SortField,
    normalize_query,
)
from {{cookiecutter.project_name}}.data.protocols import Repository, UnitOfWork


class AuditLogger(Protocol):
    """Minimal audit sink; real impl lives in platform.audit when enabled."""

    async def record(
        self,
        *,
        action: str,
        actor_id: str | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        org_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None: ...


ModelT = TypeVar("ModelT")

logger = get_logger(__name__)

ServiceFactory = Callable[..., Any]


# ---------------------------------------------------------------------------
# Errors (Problem subclasses → problem+json via register_problem_handlers)
# ---------------------------------------------------------------------------


class CrudError(Problem):
    """Base CRUD domain error."""

    def __init__(
        self,
        *,
        title: str,
        status_code: int,
        detail: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            title=title,
            status_code=status_code,
            detail=detail,
            **kwargs,
        )


class EntityNotFoundError(CrudError):
    def __init__(self, item_id: str, *, resource: str = "resource") -> None:
        super().__init__(
            title="Not Found",
            status_code=404,
            detail=f"{resource} '{item_id}' was not found",
        )


class ConflictError(CrudError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            title="Conflict",
            status_code=409,
            detail=detail,
        )


class ForbiddenError(CrudError):
    def __init__(self, detail: str = "forbidden") -> None:
        super().__init__(
            title="Forbidden",
            status_code=403,
            detail=detail,
        )


class ValidationQueryError(CrudError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            title="Bad Request",
            status_code=400,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# Configuration / context / page
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CrudConfig:
    """Per-resource CRUD behavior."""

    soft_delete: bool = True
    audit_events: bool = True

    default_page_size: int = 25
    max_page_size: int = 100
    max_bulk_size: int = 100

    allow_create: bool = True
    allow_update: bool = True
    allow_delete: bool = True
    allow_restore: bool = True
    allow_bulk: bool = True

    resource_name: str = "resource"
    cursor_sort_field: str = "id"

    read_permission: str | None = None
    write_permission: str | None = None
    delete_permission: str | None = None

    allow_list: QueryAllowList = field(default_factory=QueryAllowList)

    def __post_init__(self) -> None:
        if self.default_page_size < 1:
            raise ValueError("default_page_size must be >= 1")
        if self.max_page_size < self.default_page_size:
            raise ValueError("max_page_size must be >= default_page_size")
        if self.max_bulk_size < 1:
            raise ValueError("max_bulk_size must be >= 1")


@dataclass
class CrudContext:
    """Request-scoped CRUD context."""

    principal: Any | None = None
    org_id: str | None = None
    audit_log: AuditLogger | None = None
    unit_of_work: UnitOfWork | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class Page(Generic[ModelT]):
    """Cursor-paginated result."""

    items: list[ModelT]
    next_cursor: str | None = None


class BulkCreateBody(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class BulkUpdateItem(BaseModel):
    id: str
    data: dict[str, Any] = Field(default_factory=dict)


class BulkUpdateBody(BaseModel):
    items: list[BulkUpdateItem] = Field(default_factory=list)


class BulkDeleteBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CrudService(Generic[ModelT]):
    """
    Generic CRUD application service.

    Business modules subclass this class and override lifecycle hooks.
    """

    def __init__(
        self,
        repository: Repository[ModelT],
        *,
        config: CrudConfig | None = None,
        context: CrudContext | None = None,
    ) -> None:
        self.repository = repository
        self.config = config or CrudConfig()
        self.context = context or CrudContext()

    # ------------------------------------------------------------------
    # Authz / audit helpers
    # ------------------------------------------------------------------

    async def authorize(
        self,
        action: str,
        obj: ModelT | None = None,
    ) -> None:
        """Override for ABAC; default is a no-op (route deps handle RBAC)."""
        return None

    async def _audit(
        self,
        action: str,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self.config.audit_events:
            return
        log = self.context.audit_log
        if log is None:
            return
        actor = None
        if self.context.principal is not None:
            actor = getattr(self.context.principal, "user_id", None)
        await log.record(
            action=action,
            actor_id=actor,
            resource=self.config.resource_name,
            resource_id=resource_id,
            org_id=self.context.org_id,
            detail=detail,
        )

    async def _maybe_uow(self) -> Any:
        uow = self.context.unit_of_work
        if uow is None:
            return None
        return uow

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    async def before_create(self, data: dict[str, Any]) -> dict[str, Any]:
        return data

    async def after_create(self, obj: ModelT) -> ModelT:
        return obj

    async def before_update(self, obj: ModelT, data: dict[str, Any]) -> dict[str, Any]:
        return data

    async def after_update(self, obj: ModelT) -> ModelT:
        return obj

    async def before_delete(self, obj: ModelT) -> None:
        return None

    async def after_delete(self, obj: ModelT) -> None:
        return None

    async def before_restore(self, obj: ModelT) -> None:
        return None

    async def after_restore(self, obj: ModelT) -> ModelT:
        return obj

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(
        self,
        item_id: str,
        *,
        include_deleted: bool = False,
    ) -> ModelT:
        await self.authorize("read")
        obj = await self.repository.get(item_id, include_deleted=include_deleted)
        if obj is None:
            raise EntityNotFoundError(item_id, resource=self.config.resource_name)
        await self.authorize("read", obj)
        return obj

    def _parse_query(
        self,
        *,
        cursor: str | None,
        limit: int | None,
        filters: Sequence[FilterClause] | None,
        sort: Sequence[SortField] | None,
        search: str | None,
        include_deleted: bool,
    ) -> QuerySpec:
        requested = limit if limit is not None else self.config.default_page_size
        requested = max(1, requested)
        try:
            if cursor:
                parse_cursor(cursor)
            return normalize_query(
                QuerySpec(
                    filters=tuple(filters or ()),
                    sort=tuple(sort or ()),
                    search=search,
                    cursor=cursor,
                    limit=requested,
                    include_deleted=include_deleted,
                ),
                self.config.allow_list,
                max_limit=self.config.max_page_size,
            )
        except ValueError as exc:
            raise ValidationQueryError(str(exc)) from exc

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        filters: Sequence[FilterClause] | None = None,
        sort: Sequence[SortField] | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> Page[ModelT]:
        await self.authorize("list")
        spec = self._parse_query(
            cursor=cursor,
            limit=limit,
            filters=filters,
            sort=sort,
            search=search,
            include_deleted=include_deleted,
        )
        items = await self.repository.list(
            limit=spec.limit + 1,
            cursor=spec.cursor,
            filters=spec.filters,
            sort=spec.sort,
            search=spec.search,
            include_deleted=spec.include_deleted,
        )
        has_more = len(items) > spec.limit
        page_items = items[: spec.limit]
        next_cursor = None
        if has_more and page_items:
            next_cursor = self._make_cursor(page_items[-1])
        return Page(items=page_items, next_cursor=next_cursor)

    # ------------------------------------------------------------------
    # Create / update / delete / restore
    # ------------------------------------------------------------------

    async def create(self, data: dict[str, Any]) -> ModelT:
        if not self.config.allow_create:
            raise ForbiddenError("create is disabled for this resource")
        await self.authorize("create")
        payload = dict(data)
        if self.context.org_id and "org_id" not in payload:
            payload["org_id"] = self.context.org_id
        prepared = await self.before_create(payload)
        obj = await self.repository.create(prepared)
        result = await self.after_create(obj)
        item_id = str(getattr(result, "id", "") or "")
        await self._audit("create", item_id)
        logger.info("crud.create", extra={"resource": self.config.resource_name, "id": item_id})
        return result

    async def update(
        self,
        item_id: str,
        data: dict[str, Any],
        *,
        expected_version: int | None = None,
    ) -> ModelT:
        if not self.config.allow_update:
            raise ForbiddenError("update is disabled for this resource")
        existing = await self.get(item_id)
        await self.authorize("update", existing)
        prepared = await self.before_update(existing, dict(data))
        version = (
            expected_version
            if expected_version is not None
            else int(getattr(existing, "version", 1) or 1)
        )
        obj = await self.repository.update(
            item_id,
            prepared,
            expected_version=version,
        )
        if obj is None:
            raise EntityNotFoundError(item_id, resource=self.config.resource_name)
        result = await self.after_update(obj)
        await self._audit("update", item_id)
        logger.info("crud.update", extra={"resource": self.config.resource_name, "id": item_id})
        return result

    async def delete(self, item_id: str) -> None:
        if not self.config.allow_delete:
            raise ForbiddenError("delete is disabled for this resource")
        obj = await self.get(item_id)
        await self.authorize("delete", obj)
        await self.before_delete(obj)
        deleted = await self.repository.delete(item_id, soft=self.config.soft_delete)
        if not deleted:
            raise EntityNotFoundError(item_id, resource=self.config.resource_name)
        await self.after_delete(obj)
        await self._audit("delete", item_id)
        logger.info("crud.delete", extra={"resource": self.config.resource_name, "id": item_id})

    async def restore(self, item_id: str) -> ModelT:
        if not self.config.allow_restore or not self.config.soft_delete:
            raise ForbiddenError("restore is disabled for this resource")
        existing = await self.repository.get(item_id, include_deleted=True)
        if existing is None:
            raise EntityNotFoundError(item_id, resource=self.config.resource_name)
        await self.authorize("restore", existing)
        await self.before_restore(existing)
        obj = await self.repository.restore(item_id)
        if obj is None:
            raise EntityNotFoundError(item_id, resource=self.config.resource_name)
        result = await self.after_restore(obj)
        await self._audit("restore", item_id)
        return result

    # ------------------------------------------------------------------
    # Bulk
    # ------------------------------------------------------------------

    def _check_bulk_size(self, size: int) -> None:
        if not self.config.allow_bulk:
            raise ForbiddenError("bulk operations are disabled for this resource")
        if size < 1:
            raise ValidationQueryError("bulk payload must contain at least one item")
        if size > self.config.max_bulk_size:
            raise ValidationQueryError(
                f"bulk size {size} exceeds max_bulk_size {self.config.max_bulk_size}"
            )

    async def bulk_create(self, items: Sequence[dict[str, Any]]) -> list[ModelT]:
        self._check_bulk_size(len(items))
        await self.authorize("bulk_create")
        prepared: list[dict[str, Any]] = []
        for raw in items:
            payload = dict(raw)
            if self.context.org_id and "org_id" not in payload:
                payload["org_id"] = self.context.org_id
            prepared.append(await self.before_create(payload))
        created = await self.repository.bulk_create(prepared)
        results: list[ModelT] = []
        for obj in created:
            results.append(await self.after_create(obj))
        await self._audit("bulk_create", detail={"count": len(results)})
        return results

    async def bulk_update(
        self,
        updates: Sequence[tuple[str, dict[str, Any]]],
    ) -> list[ModelT]:
        self._check_bulk_size(len(updates))
        await self.authorize("bulk_update")
        prepared: list[tuple[str, dict[str, Any]]] = []
        for item_id, data in updates:
            existing = await self.get(item_id)
            await self.authorize("update", existing)
            prepared.append((item_id, await self.before_update(existing, dict(data))))
        updated = await self.repository.bulk_update(prepared)
        results: list[ModelT] = []
        for obj in updated:
            results.append(await self.after_update(obj))
        await self._audit("bulk_update", detail={"count": len(results)})
        return results

    async def bulk_delete(self, item_ids: Sequence[str]) -> int:
        self._check_bulk_size(len(item_ids))
        await self.authorize("bulk_delete")
        for item_id in item_ids:
            obj = await self.get(item_id)
            await self.authorize("delete", obj)
            await self.before_delete(obj)
        count = await self.repository.bulk_delete(
            item_ids,
            soft=self.config.soft_delete,
        )
        await self._audit("bulk_delete", detail={"count": count})
        return count

    def _make_cursor(self, obj: ModelT) -> str:
        sort_field = self.config.cursor_sort_field
        sort_value = getattr(obj, sort_field, None)
        item_id = getattr(obj, "id", None)
        if item_id is None:
            raise CrudError(
                title="Internal Server Error",
                status_code=500,
                detail="cannot generate cursor: entity has no id",
            )
        if sort_value is None:
            sort_value = item_id
        return make_cursor(str(sort_value), str(item_id))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize(obj: Any, schema: type[BaseModel] | None) -> Any:
    if schema is not None:
        return schema.model_validate(obj, from_attributes=True)
    if isinstance(obj, BaseModel):
        return obj
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def _parse_filter_param(raw: str | None) -> list[FilterClause]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationQueryError(f"invalid filters JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValidationQueryError("filters must be a JSON array")
    clauses: list[FilterClause] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValidationQueryError("each filter must be an object")
        try:
            op = FilterOp(str(item.get("op", "eq")))
        except ValueError as exc:
            raise ValidationQueryError(f"invalid filter op: {item.get('op')}") from exc
        field_name = item.get("field")
        if not field_name:
            raise ValidationQueryError("filter.field is required")
        clauses.append(FilterClause(field=str(field_name), op=op, value=item.get("value")))
    return clauses


def _parse_sort_param(raw: str | None) -> list[SortField]:
    if not raw:
        return []
    # format: field:asc,other:desc
    result: list[SortField] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, direction = part.split(":", 1)
        else:
            name, direction = part, "asc"
        try:
            direction_enum = SortDirection(direction.lower())
        except ValueError as exc:
            raise ValidationQueryError(f"invalid sort direction: {direction}") from exc
        result.append(SortField(field=name.strip(), direction=direction_enum))
    return result


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None or not if_match.strip():
        return None
    token = if_match.strip().strip('"')
    try:
        return int(token)
    except ValueError as exc:
        raise ValidationQueryError(f"invalid If-Match version: {if_match}") from exc


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def crud_router(
    *,
    service_factory: ServiceFactory,
    prefix: str,
    tags: list[str] | None = None,
    create_schema: type[BaseModel] | None = None,
    update_schema: type[BaseModel] | None = None,
    response_schema: type[BaseModel] | None = None,
    config: CrudConfig | None = None,
    get_audit_log: Callable[[], AuditLogger] | None = None,
) -> APIRouter:
    """
    Generate standard CRUD endpoints.

    `service_factory` owns dependency injection, authentication context,
    tenant scoping, and repository creation. It may be sync or async and
    may accept FastAPI `Depends` parameters when used as a dependency.
    """

    cfg = config or CrudConfig()
    router = APIRouter(prefix=prefix, tags=tags or [])

    async def resolve_service(request: Request) -> CrudService[Any]:
        result = service_factory()
        if hasattr(result, "__await__"):
            service = await result  # type: ignore[misc]
        else:
            service = result
        if get_audit_log is not None and service.context.audit_log is None:
            service.context.audit_log = get_audit_log()
        # Org comes from authenticated principal only — never trust X-Org-Id alone.
        # Multi-org selection: use platform.tenancy.require_tenant_context.
        if service.context.org_id is None:
            principal = service.context.principal
            if principal is not None:
                service.context.org_id = getattr(principal, "org_id", None) or None
        return service

    def _permission_deps(permission: str | None) -> list[Any]:
        if not permission:
            return []
        from {{cookiecutter.project_name}}.identity.deps import RequirePermission

        return [Depends(RequirePermission(permission))]

    @router.get("/", dependencies=_permission_deps(cfg.read_permission))
    async def list_items(
        request: Request,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=cfg.default_page_size, ge=1, le=cfg.max_page_size),
        filters: str | None = Query(default=None, description="JSON array of filter clauses"),
        sort: str | None = Query(default=None, description="field:asc,other:desc"),
        search: str | None = Query(default=None),
        include_deleted: bool = Query(default=False),
        service: CrudService[Any] = Depends(resolve_service),
    ) -> dict[str, Any]:
        page = await service.list(
            cursor=cursor,
            limit=limit,
            filters=_parse_filter_param(filters),
            sort=_parse_sort_param(sort),
            search=search,
            include_deleted=include_deleted,
        )
        return {
            "items": [serialize(item, response_schema) for item in page.items],
            "next_cursor": page.next_cursor,
        }

    # Static paths (/bulk) before /{item_id} so they are not captured as ids.
    if cfg.allow_bulk:

        @router.post(
            "/bulk",
            status_code=status.HTTP_201_CREATED,
            dependencies=_permission_deps(cfg.write_permission),
        )
        async def bulk_create_items(
            body: BulkCreateBody,
            service: CrudService[Any] = Depends(resolve_service),
        ) -> dict[str, Any]:
            created = await service.bulk_create(body.items)
            return {"items": [serialize(item, response_schema) for item in created]}

        @router.patch(
            "/bulk",
            dependencies=_permission_deps(cfg.write_permission),
        )
        async def bulk_update_items(
            body: BulkUpdateBody,
            service: CrudService[Any] = Depends(resolve_service),
        ) -> dict[str, Any]:
            updated = await service.bulk_update([(item.id, item.data) for item in body.items])
            return {"items": [serialize(item, response_schema) for item in updated]}

        @router.post(
            "/bulk/delete",
            dependencies=_permission_deps(cfg.delete_permission or cfg.write_permission),
        )
        async def bulk_delete_items(
            body: BulkDeleteBody,
            service: CrudService[Any] = Depends(resolve_service),
        ) -> dict[str, Any]:
            count = await service.bulk_delete(body.ids)
            return {"deleted": count}

    if cfg.allow_create and create_schema is not None:
        create_model = create_schema

        async def create_item(
            body: BaseModel,
            service: CrudService[Any] = Depends(resolve_service),
        ) -> Any:
            obj = await service.create(body.model_dump())
            return serialize(obj, response_schema)

        # from __future__ annotations would otherwise leave a string name FastAPI
        # cannot resolve for the dynamic body model.
        create_item.__annotations__["body"] = create_model
        router.add_api_route(
            "/",
            create_item,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            dependencies=_permission_deps(cfg.write_permission),
            response_model=response_schema,
        )

    @router.get("/{item_id}", dependencies=_permission_deps(cfg.read_permission))
    async def get_item(
        item_id: str,
        service: CrudService[Any] = Depends(resolve_service),
    ) -> Any:
        obj = await service.get(item_id)
        return serialize(obj, response_schema)

    if cfg.allow_update and update_schema is not None:
        update_model = update_schema

        async def update_item(
            item_id: str,
            body: BaseModel,
            if_match: str | None = Header(default=None, alias="If-Match"),
            service: CrudService[Any] = Depends(resolve_service),
        ) -> Any:
            obj = await service.update(
                item_id,
                body.model_dump(exclude_unset=True),
                expected_version=_parse_if_match(if_match),
            )
            return serialize(obj, response_schema)

        update_item.__annotations__["body"] = update_model
        router.add_api_route(
            "/{item_id}",
            update_item,
            methods=["PATCH"],
            dependencies=_permission_deps(cfg.write_permission),
            response_model=response_schema,
        )

    if cfg.allow_delete:

        @router.delete(
            "/{item_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            response_class=Response,
            dependencies=_permission_deps(cfg.delete_permission or cfg.write_permission),
        )
        async def delete_item(
            item_id: str,
            service: CrudService[Any] = Depends(resolve_service),
        ) -> Response:
            await service.delete(item_id)
            return Response(status_code=status.HTTP_204_NO_CONTENT)

    if cfg.soft_delete and cfg.allow_restore:

        @router.post(
            "/{item_id}/restore",
            dependencies=_permission_deps(cfg.write_permission),
        )
        async def restore_item(
            item_id: str,
            service: CrudService[Any] = Depends(resolve_service),
        ) -> Any:
            obj = await service.restore(item_id)
            return serialize(obj, response_schema)

    return router
