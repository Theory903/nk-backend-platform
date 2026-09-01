"""NK ERP feature pack: Universal DocType hub (all 534+ ERPNext doctypes)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry, agent_tool
from {{cookiecutter.project_name}}.erp.features.base import ErpFeaturePackMeta
from {{cookiecutter.project_name}}.erp.features.common.context import ErpFeatureContext
from {{cookiecutter.project_name}}.erp.features.deps import get_erp_context
from {{cookiecutter.project_name}}.erp.schemas.doctype_registry import slugify
from {{cookiecutter.project_name}}.erp.services.doctype import DoctypeRecordCreate, DoctypeService


class _Pack:
    meta = ErpFeaturePackMeta(
        id="doctype_hub",
        name="Universal DocType Hub",
        requires=("db", "documents_hub"),
    )

    def register_tools(self, registry: ToolRegistry, *, ctx: ErpFeatureContext | None = None) -> None:
        @agent_tool("List ERPNext doctypes available in NK registry")
        async def list_erp_doctypes() -> str:
            svc = DoctypeService(None, org_id="")  # type: ignore[arg-type]
            rows = svc.catalog()
            return f"doctypes={len(rows)}"

        @agent_tool("Create any ERPNext doctype record by name and JSON data")
        async def create_doctype_record(doctype: str, data_json: str) -> str:
            import json

            if ctx is None or ctx.db_session is None:
                return "unavailable"
            try:
                data = json.loads(data_json)
            except json.JSONDecodeError:
                return "invalid json"
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.create(doctype, DoctypeRecordCreate(data=data))
            except KeyError as exc:
                return str(exc)
            return f"created {row.docname} id={row.id}"

        registry.register(list_erp_doctypes)
        registry.register(create_doctype_record)

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/doctypes", tags=["erp-features"])

        @router.get("")
        async def list_all_doctypes(
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            module: str | None = None,
        ) -> list[dict[str, Any]]:
            return DoctypeService(ctx.db_session, org_id=ctx.org_id()).catalog(module=module)

        @router.get("/counts")
        async def record_counts(ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)]) -> list[dict[str, Any]]:
            return await DoctypeService(ctx.db_session, org_id=ctx.org_id()).counts_by_doctype()

        @router.get("/{doctype_slug}/meta")
        async def doctype_meta(
            doctype_slug: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            for row in svc.catalog():
                if slugify(row["name"]) == doctype_slug:
                    return svc.meta(row["name"])
            raise HTTPException(status_code=404, detail=f"doctype {doctype_slug} not found")

        @router.get("/{doctype_slug}/records")
        async def list_records(
            doctype_slug: str,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
            limit: int = 50,
        ) -> list[dict[str, Any]]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            rows = await DoctypeService(ctx.db_session, org_id=ctx.org_id()).list_records(doctype, limit=limit)
            return [r.model_dump(mode="json") for r in rows]

        @router.post("/{doctype_slug}/records")
        async def create_record(
            doctype_slug: str,
            payload: DoctypeRecordCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.create(doctype, payload)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.get("/{doctype_slug}/records/{record_id}")
        async def get_record(
            doctype_slug: str,
            record_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            row = await DoctypeService(ctx.db_session, org_id=ctx.org_id()).get(doctype, record_id)
            if row is None:
                raise HTTPException(status_code=404, detail="record not found")
            from {{cookiecutter.project_name}}.erp.services.doctype import DoctypeRecordRead

            return DoctypeRecordRead.model_validate(row, from_attributes=True).model_dump(mode="json")

        @router.put("/{doctype_slug}/records/{record_id}")
        async def update_record(
            doctype_slug: str,
            record_id: uuid.UUID,
            payload: DoctypeRecordCreate,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.update(doctype, record_id, payload)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/{doctype_slug}/records/{record_id}/submit")
        async def submit_record(
            doctype_slug: str,
            record_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.submit(doctype, record_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/{doctype_slug}/records/{record_id}/cancel")
        async def cancel_record(
            doctype_slug: str,
            record_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.cancel(doctype, record_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        @router.post("/{doctype_slug}/records/{record_id}/amend")
        async def amend_record(
            doctype_slug: str,
            record_id: uuid.UUID,
            ctx: Annotated[ErpFeatureContext, Depends(get_erp_context)],
        ) -> dict[str, Any]:
            doctype = _resolve_doctype(doctype_slug, ctx)
            svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
            try:
                row = await svc.amend(doctype, record_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return row.model_dump(mode="json")

        return router


def _resolve_doctype(slug: str, ctx: ErpFeatureContext) -> str:
    svc = DoctypeService(ctx.db_session, org_id=ctx.org_id())
    for row in svc.catalog():
        if slugify(row["name"]) == slug:
            return row["name"]
    raise HTTPException(status_code=404, detail=f"doctype {slug} not found")


PACK = _Pack()
