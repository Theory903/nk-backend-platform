"""Master data persistence service."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.db.models.erp import (
    ErpCustomer,
    ErpItem,
    ErpPaymentTerm,
    ErpPaymentTermsTemplate,
    ErpSupplier,
)
from {{cookiecutter.project_name}}.erp.schemas.masters import (
    CustomerCreate,
    CustomerRead,
    ItemCreate,
    ItemRead,
    PaymentTermCreate,
    PaymentTermRead,
    PaymentTermsTemplateCreate,
    PaymentTermsTemplateRead,
    SupplierCreate,
    SupplierRead,
)


class MastersService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id

    async def create_item(self, payload: ItemCreate) -> ItemRead:
        row = ErpItem(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return ItemRead.model_validate(row, from_attributes=True)

    async def list_items(self, *, limit: int = 50) -> list[ItemRead]:
        stmt = (
            select(ErpItem)
            .where(ErpItem.org_id == self._org_id)
            .order_by(ErpItem.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [ItemRead.model_validate(row, from_attributes=True) for row in rows]

    async def get_item_by_code(self, item_code: str) -> ErpItem | None:
        stmt = select(ErpItem).where(
            ErpItem.org_id == self._org_id,
            ErpItem.item_code == item_code,
        )
        return await self._session.scalar(stmt)

    async def create_customer(self, payload: CustomerCreate) -> CustomerRead:
        row = ErpCustomer(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return CustomerRead.model_validate(row, from_attributes=True)

    async def list_customers(self, *, limit: int = 50) -> list[CustomerRead]:
        stmt = (
            select(ErpCustomer)
            .where(ErpCustomer.org_id == self._org_id)
            .order_by(ErpCustomer.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [CustomerRead.model_validate(row, from_attributes=True) for row in rows]

    async def create_supplier(self, payload: SupplierCreate) -> SupplierRead:
        row = ErpSupplier(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return SupplierRead.model_validate(row, from_attributes=True)

    async def list_suppliers(self, *, limit: int = 50) -> list[SupplierRead]:
        stmt = (
            select(ErpSupplier)
            .where(ErpSupplier.org_id == self._org_id)
            .order_by(ErpSupplier.created_at.desc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [SupplierRead.model_validate(row, from_attributes=True) for row in rows]

    async def get_customer(self, customer_id: uuid.UUID) -> ErpCustomer | None:
        stmt = select(ErpCustomer).where(
            ErpCustomer.org_id == self._org_id,
            ErpCustomer.id == customer_id,
        )
        return await self._session.scalar(stmt)

    async def create_payment_term(self, payload: PaymentTermCreate) -> PaymentTermRead:
        row = ErpPaymentTerm(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return PaymentTermRead.model_validate(row, from_attributes=True)

    async def list_payment_terms(self, *, limit: int = 200) -> list[PaymentTermRead]:
        stmt = (
            select(ErpPaymentTerm)
            .where(ErpPaymentTerm.org_id == self._org_id)
            .order_by(ErpPaymentTerm.payment_term_name.asc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [PaymentTermRead.model_validate(row, from_attributes=True) for row in rows]

    async def create_payment_terms_template(
        self, payload: PaymentTermsTemplateCreate
    ) -> PaymentTermsTemplateRead:
        row = ErpPaymentTermsTemplate(org_id=self._org_id, **payload.model_dump())
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return PaymentTermsTemplateRead.model_validate(row, from_attributes=True)

    async def list_payment_terms_templates(
        self, *, limit: int = 100
    ) -> list[PaymentTermsTemplateRead]:
        stmt = (
            select(ErpPaymentTermsTemplate)
            .where(ErpPaymentTermsTemplate.org_id == self._org_id)
            .order_by(ErpPaymentTermsTemplate.template_name.asc())
            .limit(limit)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [
            PaymentTermsTemplateRead.model_validate(row, from_attributes=True) for row in rows
        ]

    async def lookup_party(self, party_type: str, name: str) -> dict[str, str] | None:
        needle = name.strip().lower()
        if party_type.lower() == "customer":
            rows = await self.list_customers(limit=200)
            for row in rows:
                if needle in row.customer_name.lower():
                    return {"party_type": "Customer", "party_id": str(row.id), "name": row.customer_name}
        if party_type.lower() == "supplier":
            rows = await self.list_suppliers(limit=200)
            for row in rows:
                if needle in row.supplier_name.lower():
                    return {"party_type": "Supplier", "party_id": str(row.id), "name": row.supplier_name}
        item = await self.get_item_by_code(name)
        if item is not None:
            return {"party_type": "Item", "party_id": str(item.id), "name": item.item_code}
        return None
