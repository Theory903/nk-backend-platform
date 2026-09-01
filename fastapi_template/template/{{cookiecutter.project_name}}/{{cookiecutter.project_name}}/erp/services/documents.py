"""Generic ERP document persistence, lifecycle, and mapping."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import ErpDocument
from {{cookiecutter.project_name}}.erp.schemas.documents import DocumentCreate, DocumentLine, DocumentRead
from {{cookiecutter.project_name}}.erp.schemas.transaction import TaxLine, TransactionDocument
from {{cookiecutter.project_name}}.erp.services.controller_replica import ControllerReplica
from {{cookiecutter.project_name}}.erp.services.lifecycle import CANCELLABLE, DocStatus, SUBMITTABLE
from {{cookiecutter.project_name}}.erp.services.payment_schedule import build_payment_schedule
from {{cookiecutter.project_name}}.erp.services.posting import PostingService
from {{cookiecutter.project_name}}.erp.services.pricing import PricingService
from {{cookiecutter.project_name}}.erp.services.status_engine import document_status_payload, resolve_status


def _today() -> date:
    return date.today()


class DocumentService:
    """CRUD + ERPNext lifecycle for all transaction documents."""

    _pricing = PricingService()

    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._seq: dict[str, int] = {}

    def _next_name(self, doctype: str) -> str:
        self._seq[doctype] = self._seq.get(doctype, 0) + 1
        prefix = doctype.upper().replace("_", "-")[:3]
        return f"{prefix}-{self._seq[doctype]:05d}"

    def _calc_totals(self, payload: DocumentCreate) -> dict[str, Any]:
        doc = TransactionDocument(
            currency=payload.currency,
            conversion_rate=payload.conversion_rate,
            apply_discount_on=payload.apply_discount_on,
            additional_discount_percentage=payload.additional_discount_percentage,
            discount_amount=payload.discount_amount,
            shipping_amount=payload.shipping_amount,
            items=[line.model_dump() for line in payload.lines],
            taxes=[tax.model_dump() for tax in payload.taxes],
        )
        totals = self._pricing.calculate(doc)
        result = totals.model_dump()
        result["grand_total"] = totals.rounded_total or totals.grand_total
        return result

    async def create(self, doctype: str, payload: DocumentCreate, *, status: str = "Draft") -> DocumentRead:
        replica = ControllerReplica()
        raw = {
            "company": payload.company,
            "customer_id": str(payload.customer_id) if payload.customer_id else None,
            "supplier_id": str(payload.supplier_id) if payload.supplier_id else None,
            "items": [line.model_dump(mode="json") for line in payload.lines],
            "taxes": [tax.model_dump(mode="json") for tax in payload.taxes],
        }
        errors = replica.validate(self._erpnext_doctype_name(doctype), raw, action="save")
        if errors:
            raise ValueError("; ".join(errors))
        totals = self._calc_totals(payload)
        meta = dict(payload.meta)
        if doctype in {"sales_invoice", "purchase_invoice", "sales_order"} and "payment_schedule" not in meta:
            meta["payment_schedule"] = build_payment_schedule(
                float(totals.get("grand_total") or 0),
                payload.posting_date or _today(),
                terms=meta.get("payment_schedule_terms"),
                template_id=meta.get("payment_terms_template"),
            )
        row = ErpDocument(
            org_id=self._org_id,
            doctype=doctype,
            docname=self._next_name(doctype),
            status=status,
            docstatus=DocStatus.DRAFT,
            company=payload.company,
            currency=payload.currency,
            party_type=payload.party_type,
            party_id=payload.party_id,
            customer_id=payload.customer_id,
            supplier_id=payload.supplier_id,
            posting_date=payload.posting_date or _today(),
            lines=[line.model_dump(mode="json") for line in payload.lines],
            taxes=[tax.model_dump(mode="json") for tax in payload.taxes],
            totals=totals,
            meta=meta,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return self._read(row)

    async def get(self, doc_id: uuid.UUID) -> ErpDocument | None:
        stmt = select(ErpDocument).where(ErpDocument.org_id == self._org_id, ErpDocument.id == doc_id)
        return await self._session.scalar(stmt)

    async def list_by_type(self, doctype: str, *, limit: int = 50) -> list[DocumentRead]:
        stmt = (
            select(ErpDocument)
            .where(ErpDocument.org_id == self._org_id, ErpDocument.doctype == doctype)
            .order_by(ErpDocument.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [self._read(row) for row in rows]

    async def submit(self, doc_id: uuid.UUID) -> DocumentRead:
        row = await self.get(doc_id)
        if row is None:
            raise LookupError(f"document {doc_id} not found")
        if DocStatus(row.docstatus) not in SUBMITTABLE:
            raise ValueError("only draft documents can be submitted")
        replica = ControllerReplica()
        submit_data = {
            "customer_id": str(row.customer_id) if row.customer_id else None,
            "supplier_id": str(row.supplier_id) if row.supplier_id else None,
            "company": row.company,
            "items": row.lines,
            "taxes": row.taxes,
        }
        errors = replica.validate(self._erpnext_doctype_name(row.doctype), submit_data, action="submit")
        if errors:
            raise ValueError("; ".join(errors))
        row.docstatus = DocStatus.SUBMITTED
        row.status = resolve_status(row.doctype, document_status_payload(row))
        posting = PostingService(self._session, org_id=self._org_id)
        post_result = await posting.on_submit(row)
        row.meta = {**row.meta, "posting": post_result}
        await self._session.flush()
        await self._session.refresh(row)
        return self._read(row)

    async def cancel(self, doc_id: uuid.UUID) -> DocumentRead:
        row = await self.get(doc_id)
        if row is None:
            raise LookupError(f"document {doc_id} not found")
        if DocStatus(row.docstatus) not in CANCELLABLE:
            raise ValueError("only submitted documents can be cancelled")
        row.docstatus = DocStatus.CANCELLED
        row.status = "Cancelled"
        await self._session.flush()
        await self._session.refresh(row)
        return self._read(row)

    async def amend(self, doc_id: uuid.UUID) -> DocumentRead:
        source = await self.get(doc_id)
        if source is None:
            raise LookupError(f"document {doc_id} not found")
        if DocStatus(source.docstatus) != DocStatus.SUBMITTED:
            raise ValueError("only submitted documents can be amended")
        payload = DocumentCreate(
            party_type=source.party_type,
            party_id=source.party_id,
            customer_id=source.customer_id,
            supplier_id=source.supplier_id,
            company=source.company,
            currency=source.currency,
            posting_date=source.posting_date,
            lines=[DocumentLine.model_validate(line) for line in source.lines],
            taxes=[TaxLine.model_validate(tax) for tax in source.taxes],
            meta={**source.meta, "amended_from": str(source.id)},
        )
        await self.cancel(doc_id)
        created = await self.create(source.doctype, payload)
        amended = await self.get(created.id)
        if amended is not None:
            amended.amended_from = source.id
            await self._session.flush()
            await self._session.refresh(amended)
            return self._read(amended)
        return created

    async def set_status(self, doc_id: uuid.UUID, status: str) -> DocumentRead:
        row = await self.get(doc_id)
        if row is None:
            raise LookupError(f"document {doc_id} not found")
        row.status = status
        await self._session.flush()
        await self._session.refresh(row)
        return self._read(row)

    async def map_document(
        self,
        source_id: uuid.UUID,
        target_doctype: str,
        *,
        status: str = "Draft",
    ) -> DocumentRead:
        source = await self.get(source_id)
        if source is None:
            raise LookupError(f"source document {source_id} not found")
        payload = DocumentCreate(
            party_type=source.party_type,
            party_id=source.party_id,
            customer_id=source.customer_id,
            supplier_id=source.supplier_id,
            company=source.company,
            currency=source.currency,
            lines=[DocumentLine.model_validate(line) for line in source.lines],
            taxes=[TaxLine.model_validate(tax) for tax in source.taxes],
            meta={**source.meta, "source_doctype": source.doctype, "source_id": str(source.id)},
        )
        created = await self.create(target_doctype, payload, status=status)
        if source.doctype == "sales_order" and target_doctype == "delivery_note":
            source.per_delivered = 100.0
            source.status = resolve_status(source.doctype, document_status_payload(source))
        if source.doctype == "sales_order" and target_doctype == "sales_invoice":
            source.per_billed = 100.0
            source.status = resolve_status(source.doctype, document_status_payload(source))
        if source.doctype == "purchase_order" and target_doctype == "purchase_receipt":
            source.per_delivered = 100.0
            source.status = resolve_status(source.doctype, document_status_payload(source))
        if source.doctype == "purchase_order" and target_doctype == "purchase_invoice":
            source.per_billed = 100.0
            source.status = resolve_status(source.doctype, document_status_payload(source))
        await self._session.flush()
        return created

    def _read(self, row: ErpDocument) -> DocumentRead:
        data = DocumentRead.model_validate(row, from_attributes=True)
        data.erpnext_status = resolve_status(row.doctype, document_status_payload(row))
        return data

    @staticmethod
    def _erpnext_doctype_name(internal: str) -> str:
        mapping = {
            "sales_order": "Sales Order",
            "quotation": "Quotation",
            "delivery_note": "Delivery Note",
            "sales_invoice": "Sales Invoice",
            "purchase_order": "Purchase Order",
            "purchase_receipt": "Purchase Receipt",
            "purchase_invoice": "Purchase Invoice",
            "request_for_quotation": "Request for Quotation",
        }
        return mapping.get(internal, internal.replace("_", " ").title())
