"""Universal CRUD for all ERPNext DocTypes."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpDoctypeRecord
from {{cookiecutter.project_name}}.erp.schemas.doctype_registry import get_doctype_meta, list_doctypes
from {{cookiecutter.project_name}}.erp.services.controller_replica import ControllerReplica
from {{cookiecutter.project_name}}.erp.services.doctype_hooks import DoctypeHookService
from {{cookiecutter.project_name}}.erp.services.lifecycle import CANCELLABLE, DocStatus, SUBMITTABLE


class DoctypeRecordCreate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    docname: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class DoctypeRecordRead(BaseModel):
    id: uuid.UUID
    org_id: str
    doctype: str
    docname: str
    docstatus: int
    is_submittable: bool
    module: str | None
    data: dict[str, Any]
    meta: dict[str, Any]

    model_config = {"from_attributes": True}


class DoctypeService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._seq: dict[str, int] = {}

    def catalog(self, *, module: str | None = None) -> list[dict[str, Any]]:
        return list_doctypes(module=module)

    def meta(self, doctype: str) -> dict[str, Any]:
        row = get_doctype_meta(doctype)
        if row is None:
            raise KeyError(f"doctype {doctype!r} not in registry")
        return row

    def _next_docname(self, doctype: str) -> str:
        self._seq[doctype] = self._seq.get(doctype, 0) + 1
        prefix = doctype.upper().replace(" ", "-")[:4]
        return f"{prefix}-{self._seq[doctype]:06d}"

    async def create(self, doctype: str, payload: DoctypeRecordCreate) -> DoctypeRecordRead:
        meta = self.meta(doctype)
        docname = payload.docname or self._next_docname(doctype)
        replica = ControllerReplica()
        data = replica.enrich_defaults(doctype, payload.data)
        errors = replica.validate(doctype, data, action="save")
        if errors:
            raise ValueError("; ".join(errors))
        row = ErpDoctypeRecord(
            org_id=self._org_id,
            doctype=doctype,
            docname=docname,
            docstatus=DocStatus.DRAFT,
            is_submittable=bool(meta.get("is_submittable")),
            module=meta.get("module"),
            data=data,
            meta=payload.meta,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return DoctypeRecordRead.model_validate(row, from_attributes=True)

    async def get(self, doctype: str, record_id: uuid.UUID) -> ErpDoctypeRecord | None:
        return await self._session.scalar(
            select(ErpDoctypeRecord).where(
                ErpDoctypeRecord.org_id == self._org_id,
                ErpDoctypeRecord.doctype == doctype,
                ErpDoctypeRecord.id == record_id,
            )
        )

    async def list_records(self, doctype: str, *, limit: int = 50) -> list[DoctypeRecordRead]:
        stmt = (
            select(ErpDoctypeRecord)
            .where(ErpDoctypeRecord.org_id == self._org_id, ErpDoctypeRecord.doctype == doctype)
            .order_by(ErpDoctypeRecord.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [DoctypeRecordRead.model_validate(r, from_attributes=True) for r in rows]

    async def update(
        self, doctype: str, record_id: uuid.UUID, payload: DoctypeRecordCreate
    ) -> DoctypeRecordRead:
        row = await self.get(doctype, record_id)
        if row is None:
            raise LookupError(f"record {record_id} not found")
        if DocStatus(row.docstatus) != DocStatus.DRAFT:
            raise ValueError("only draft records can be updated")
        row.data = {**row.data, **payload.data}
        row.meta = {**row.meta, **payload.meta}
        await self._session.flush()
        await self._session.refresh(row)
        return DoctypeRecordRead.model_validate(row, from_attributes=True)

    async def submit(self, doctype: str, record_id: uuid.UUID) -> DoctypeRecordRead:
        row = await self.get(doctype, record_id)
        if row is None:
            raise LookupError(f"record {record_id} not found")
        if not row.is_submittable:
            raise ValueError(f"{doctype} is not submittable")
        if DocStatus(row.docstatus) not in SUBMITTABLE:
            raise ValueError("only draft records can be submitted")
        replica = ControllerReplica()
        errors = replica.validate(doctype, row.data or {}, action="submit")
        if errors:
            raise ValueError("; ".join(errors))
        row.docstatus = DocStatus.SUBMITTED
        hooks = DoctypeHookService(self._session, org_id=self._org_id)
        hook_result = await hooks.on_submit(row)
        row.meta = {**row.meta, "hooks": hook_result}
        await self._session.flush()
        await self._session.refresh(row)
        return DoctypeRecordRead.model_validate(row, from_attributes=True)

    async def cancel(self, doctype: str, record_id: uuid.UUID) -> DoctypeRecordRead:
        row = await self.get(doctype, record_id)
        if row is None:
            raise LookupError(f"record {record_id} not found")
        if DocStatus(row.docstatus) not in CANCELLABLE:
            raise ValueError("only submitted records can be cancelled")
        row.docstatus = DocStatus.CANCELLED
        hooks = DoctypeHookService(self._session, org_id=self._org_id)
        hook_result = await hooks.on_cancel(row)
        row.meta = {**row.meta, "hooks": {**(row.meta.get("hooks") or {}), "cancel": hook_result}}
        await self._session.flush()
        await self._session.refresh(row)
        return DoctypeRecordRead.model_validate(row, from_attributes=True)

    async def amend(self, doctype: str, record_id: uuid.UUID) -> DoctypeRecordRead:
        source = await self.get(doctype, record_id)
        if source is None:
            raise LookupError(f"record {record_id} not found")
        if DocStatus(source.docstatus) != DocStatus.SUBMITTED:
            raise ValueError("only submitted records can be amended")
        await self.cancel(doctype, record_id)
        created = await self.create(
            doctype,
            DoctypeRecordCreate(
                data={**source.data},
                meta={**source.meta, "amended_from": str(source.id)},
            ),
        )
        return created

    async def counts_by_doctype(self) -> list[dict[str, Any]]:
        stmt = (
            select(ErpDoctypeRecord.doctype, func.count(ErpDoctypeRecord.id).label("count"))
            .where(ErpDoctypeRecord.org_id == self._org_id)
            .group_by(ErpDoctypeRecord.doctype)
            .order_by(ErpDoctypeRecord.doctype)
        )
        rows = (await self._session.execute(stmt)).all()
        return [{"doctype": dt, "count": int(count)} for dt, count in rows]
