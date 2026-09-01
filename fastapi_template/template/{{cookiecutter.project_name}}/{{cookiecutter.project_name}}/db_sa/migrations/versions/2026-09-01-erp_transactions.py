{%- if cookiecutter.orm != "sqlalchemy" %}
"""ERP transaction tables — SQLAlchemy only."""

revision = "erp_txn_20260901"
down_revision = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
{%- else %}
"""ERP transaction, ledger, and operations tables."""

import sqlalchemy as sa
from alembic import op

revision = "erp_txn_20260901"
down_revision = "erp_core_20260901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doctype", sa.String(64), nullable=False, index=True),
        sa.Column("docname", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("party_type", sa.String(32)),
        sa.Column("party_id", sa.Uuid()),
        sa.Column("customer_id", sa.Uuid()),
        sa.Column("supplier_id", sa.Uuid()),
        sa.Column("posting_date", sa.Date()),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("taxes", sa.JSON(), nullable=False),
        sa.Column("totals", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
    )
    op.create_table(
        "erp_gl_entry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account", sa.String(128), nullable=False, index=True),
        sa.Column("debit", sa.Float(), nullable=False),
        sa.Column("credit", sa.Float(), nullable=False),
        sa.Column("voucher_type", sa.String(64)),
        sa.Column("voucher_id", sa.Uuid()),
        sa.Column("posting_date", sa.Date(), nullable=False),
    )
    op.create_table(
        "erp_stock_ledger_entry",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False, index=True),
        sa.Column("warehouse", sa.String(64), nullable=False, index=True),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("valuation_rate", sa.Float(), nullable=False),
        sa.Column("voucher_type", sa.String(64), nullable=False),
        sa.Column("voucher_id", sa.Uuid(), nullable=False),
    )
    op.create_table(
        "erp_project",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("percent_complete", sa.Float(), nullable=False),
        sa.Column("customer_id", sa.Uuid()),
    )
    op.create_table(
        "erp_task",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
    )
    op.create_table(
        "erp_timesheet",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("employee_name", sa.String(200), nullable=False),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "erp_bom",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
    )
    op.create_table(
        "erp_work_order",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("production_item", sa.String(64), nullable=False),
        sa.Column("bom_id", sa.Uuid()),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_table(
        "erp_asset",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset_name", sa.String(200), nullable=False),
        sa.Column("item_code", sa.String(64)),
        sa.Column("gross_purchase_amount", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("depreciation_method", sa.String(32), nullable=False),
    )
    op.create_table(
        "erp_quality_inspection",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inspection_type", sa.String(64), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("readings", sa.JSON(), nullable=False),
    )
    op.create_table(
        "erp_maintenance_visit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_id", sa.Uuid()),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    op.create_table(
        "erp_payment_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("party_type", sa.String(32), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("voucher_type", sa.String(64), nullable=False),
        sa.Column("voucher_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("outstanding", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "erp_payment_ledger",
        "erp_maintenance_visit",
        "erp_quality_inspection",
        "erp_asset",
        "erp_work_order",
        "erp_bom",
        "erp_timesheet",
        "erp_task",
        "erp_project",
        "erp_stock_ledger_entry",
        "erp_gl_entry",
        "erp_document",
    ):
        op.drop_table(table)
{%- endif %}
