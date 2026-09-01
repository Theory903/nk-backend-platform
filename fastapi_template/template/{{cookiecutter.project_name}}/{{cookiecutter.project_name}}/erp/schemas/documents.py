"""Shared ERP transaction document schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.erp.schemas.transaction import ItemLine, TaxLine


class DocumentLine(ItemLine):
    warehouse: str | None = None
    delivered_qty: float = 0.0
    billed_qty: float = 0.0


class DocumentCreate(BaseModel):
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    posting_date: date | None = None
    company: str = "NK Default"
    currency: str = "USD"
    conversion_rate: float = Field(default=1.0, gt=0)
    apply_discount_on: str = "Grand Total"
    additional_discount_percentage: float = Field(default=0.0, ge=0, le=100)
    discount_amount: float = Field(default=0.0, ge=0)
    shipping_amount: float = Field(default=0.0, ge=0)
    lines: list[DocumentLine] = Field(default_factory=list)
    taxes: list[TaxLine] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class DocumentRead(BaseModel):
    id: uuid.UUID
    org_id: str
    doctype: str
    docname: str
    status: str
    docstatus: int = 0
    per_delivered: float = 0.0
    per_billed: float = 0.0
    amended_from: uuid.UUID | None = None
    company: str = "NK Default"
    currency: str = "USD"
    party_type: str | None = None
    party_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    posting_date: date | None = None
    lines: list[dict[str, Any]]
    taxes: list[dict[str, Any]]
    totals: dict[str, Any]
    meta: dict[str, Any]
    erpnext_status: str | None = None
    created_at: datetime
    updated_at: datetime


class MapDocumentRequest(BaseModel):
    target_doctype: str
    qty_map: dict[str, float] | None = None
