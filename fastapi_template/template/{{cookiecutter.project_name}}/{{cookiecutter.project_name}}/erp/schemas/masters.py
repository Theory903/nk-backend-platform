"""Master data schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    item_code: str = Field(min_length=1, max_length=64)
    item_name: str = Field(min_length=1, max_length=200)
    item_group: str = Field(default="Products", max_length=100)
    stock_uom: str = Field(default="Nos", max_length=32)
    standard_rate: float = Field(default=0.0, ge=0)
    is_stock_item: bool = True


class ItemRead(ItemCreate):
    id: uuid.UUID
    org_id: str
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=200)
    customer_type: str = Field(default="Company", max_length=32)
    territory: str | None = None
    email_id: str | None = None
    mobile_no: str | None = None


class CustomerRead(CustomerCreate):
    id: uuid.UUID
    org_id: str
    created_at: datetime
    updated_at: datetime


class SupplierCreate(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    supplier_type: str = Field(default="Company", max_length=32)
    country: str | None = None
    email_id: str | None = None


class SupplierRead(SupplierCreate):
    id: uuid.UUID
    org_id: str
    created_at: datetime
    updated_at: datetime


class PaymentTermCreate(BaseModel):
    payment_term_name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    invoice_portion: float = Field(default=0.0, ge=0)
    mode_of_payment: str | None = None
    due_date_based_on: str | None = None
    credit_days: int = Field(default=0, ge=0)
    credit_months: int = Field(default=0, ge=0)


class PaymentTermRead(PaymentTermCreate):
    id: uuid.UUID
    org_id: str
    created_at: datetime
    updated_at: datetime


class PaymentTermsTemplateCreate(BaseModel):
    template_name: str = Field(min_length=1, max_length=128)
    allocate_payment_based_on_payment_terms: bool = False
    terms: list[dict[str, Any]] = Field(default_factory=list)


class PaymentTermsTemplateRead(PaymentTermsTemplateCreate):
    id: uuid.UUID
    org_id: str
    created_at: datetime
    updated_at: datetime
