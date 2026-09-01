"""Shared ERP SQLAlchemy mixins."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from {{cookiecutter.project_name}}.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ErpOrgMixin:
    """Tenant-scoped ERP row."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class ErpItem(Base, ErpOrgMixin):
    __tablename__ = "erp_item"

    item_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_group: Mapped[str] = mapped_column(String(100), default="Products", nullable=False)
    stock_uom: Mapped[str] = mapped_column(String(32), default="Nos", nullable=False)
    standard_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_stock_item: Mapped[bool] = mapped_column(default=True, nullable=False)


class ErpCustomer(Base, ErpOrgMixin):
    __tablename__ = "erp_customer"

    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(32), default="Company", nullable=False)
    territory: Mapped[str | None] = mapped_column(String(100))
    email_id: Mapped[str | None] = mapped_column(String(255))
    mobile_no: Mapped[str | None] = mapped_column(String(64))


class ErpSupplier(Base, ErpOrgMixin):
    __tablename__ = "erp_supplier"

    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_type: Mapped[str] = mapped_column(String(32), default="Company", nullable=False)
    country: Mapped[str | None] = mapped_column(String(100))
    email_id: Mapped[str | None] = mapped_column(String(255))


class ErpPaymentTerm(Base, ErpOrgMixin):
    __tablename__ = "erp_payment_term"

    payment_term_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    invoice_portion: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mode_of_payment: Mapped[str | None] = mapped_column(String(64))
    due_date_based_on: Mapped[str | None] = mapped_column(String(64))
    credit_days: Mapped[int] = mapped_column(default=0, nullable=False)
    credit_months: Mapped[int] = mapped_column(default=0, nullable=False)


class ErpPaymentTermsTemplate(Base, ErpOrgMixin):
    __tablename__ = "erp_payment_terms_template"

    template_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    allocate_payment_based_on_payment_terms: Mapped[bool] = mapped_column(default=False, nullable=False)
    terms: Mapped[list] = mapped_column(JSON, default=list)


class ErpLead(Base, ErpOrgMixin):
    __tablename__ = "erp_lead"

    lead_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    company_name: Mapped[str | None] = mapped_column(String(200))
    email_id: Mapped[str | None] = mapped_column(String(255))
    mobile_no: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="Lead", nullable=False)
    source: Mapped[str | None] = mapped_column(String(100))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class ErpOpportunity(Base, ErpOrgMixin):
    __tablename__ = "erp_opportunity"

    opportunity_from: Mapped[str] = mapped_column(String(32), default="Lead", nullable=False)
    party_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Open", nullable=False)
    sales_stage: Mapped[str] = mapped_column(String(64), default="Prospecting", nullable=False)
    probability: Mapped[float] = mapped_column(default=10.0, nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class ErpIssue(Base, ErpOrgMixin):
    __tablename__ = "erp_issue"

    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None]
    priority: Mapped[str] = mapped_column(String(32), default="Medium", nullable=False)
    issue_type: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="Open", nullable=False)
    agreement_status: Mapped[str | None] = mapped_column(String(64))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    response_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_resolution_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issue_split_from: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class ErpDocument(Base, ErpOrgMixin):
    __tablename__ = "erp_document"

    doctype: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    docname: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Draft", nullable=False)
    docstatus: Mapped[int] = mapped_column(default=0, nullable=False)
    per_delivered: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    per_billed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    amended_from: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    company: Mapped[str] = mapped_column(String(128), default="NK Default", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    party_type: Mapped[str | None] = mapped_column(String(32))
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    posting_date: Mapped[date | None] = mapped_column(Date())
    lines: Mapped[list] = mapped_column(JSON, default=list)
    taxes: Mapped[list] = mapped_column(JSON, default=list)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class ErpGlEntry(Base, ErpOrgMixin):
    __tablename__ = "erp_gl_entry"

    account: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    debit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    credit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    voucher_type: Mapped[str | None] = mapped_column(String(64))
    voucher_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    posting_date: Mapped[date] = mapped_column(Date(), nullable=False)


class ErpStockLedgerEntry(Base, ErpOrgMixin):
    __tablename__ = "erp_stock_ledger_entry"

    item_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    warehouse: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    valuation_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(64), nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class ErpProject(Base, ErpOrgMixin):
    __tablename__ = "erp_project"

    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Open", nullable=False)
    percent_complete: Mapped[float] = mapped_column(default=0.0, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class ErpTask(Base, ErpOrgMixin):
    __tablename__ = "erp_task"

    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), default="Open", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="Medium", nullable=False)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)


class ErpTimesheet(Base, ErpOrgMixin):
    __tablename__ = "erp_timesheet"

    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    billable: Mapped[bool] = mapped_column(default=True, nullable=False)


class ErpBom(Base, ErpOrgMixin):
    __tablename__ = "erp_bom"

    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[float] = mapped_column(default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    items: Mapped[list] = mapped_column(JSON, default=list)


class ErpWorkOrder(Base, ErpOrgMixin):
    __tablename__ = "erp_work_order"

    production_item: Mapped[str] = mapped_column(String(64), nullable=False)
    bom_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    qty: Mapped[float] = mapped_column(default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Draft", nullable=False)


class ErpAsset(Base, ErpOrgMixin):
    __tablename__ = "erp_asset"

    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_code: Mapped[str | None] = mapped_column(String(64))
    gross_purchase_amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Draft", nullable=False)
    depreciation_method: Mapped[str] = mapped_column(String(32), default="Straight Line")


class ErpQualityInspection(Base, ErpOrgMixin):
    __tablename__ = "erp_quality_inspection"

    inspection_type: Mapped[str] = mapped_column(String(64), default="Incoming", nullable=False)
    item_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Accepted", nullable=False)
    readings: Mapped[list] = mapped_column(JSON, default=list)


class ErpMaintenanceVisit(Base, ErpOrgMixin):
    __tablename__ = "erp_maintenance_visit"

    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Draft", nullable=False)


class ErpPaymentLedger(Base, ErpOrgMixin):
    __tablename__ = "erp_payment_ledger"

    party_type: Mapped[str] = mapped_column(String(32), nullable=False)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(64), nullable=False)
    voucher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    outstanding: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    payment_term: Mapped[str | None] = mapped_column(String(128))
    due_date: Mapped[date | None] = mapped_column(Date())


class ErpBankTransaction(Base, ErpOrgMixin):
    __tablename__ = "erp_bank_transaction"

    bank_account: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    posting_date: Mapped[date] = mapped_column(Date(), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    deposit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    withdrawal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128))
    is_reconciled: Mapped[bool] = mapped_column(default=False, nullable=False)
    matched_voucher_type: Mapped[str | None] = mapped_column(String(64))
    matched_voucher_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class ErpDoctypeRecord(Base, ErpOrgMixin):
    """Universal ERPNext DocType store — all 534+ doctypes via JSON payload."""

    __tablename__ = "erp_doctype_record"

    doctype: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    docname: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    docstatus: Mapped[int] = mapped_column(default=0, nullable=False)
    is_submittable: Mapped[bool] = mapped_column(default=False, nullable=False)
    module: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
