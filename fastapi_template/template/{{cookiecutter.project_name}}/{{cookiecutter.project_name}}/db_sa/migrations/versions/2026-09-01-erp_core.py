{%- if cookiecutter.orm != "sqlalchemy" %}
"""ERP core tables — SQLAlchemy only."""

revision = "erp_core_20260901"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
{%- else %}
"""ERP core master, CRM, and support tables."""

import sqlalchemy as sa
from alembic import op

revision = "erp_core_20260901"
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
down_revision = "tenant_rls_20260831"
{%- elif cookiecutter.add_dummy in [True, "True", "true", 1, "1"] %}
down_revision = "2b7380507a71"
{%- else %}
down_revision = "819cbf6e030b"
{%- endif %}
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False, index=True),
        sa.Column("item_name", sa.String(200), nullable=False),
        sa.Column("item_group", sa.String(100), nullable=False),
        sa.Column("stock_uom", sa.String(32), nullable=False),
        sa.Column("standard_rate", sa.Float(), nullable=False),
        sa.Column("is_stock_item", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "erp_customer",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_type", sa.String(32), nullable=False),
        sa.Column("territory", sa.String(100)),
        sa.Column("email_id", sa.String(255)),
        sa.Column("mobile_no", sa.String(64)),
    )
    op.create_table(
        "erp_supplier",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supplier_name", sa.String(200), nullable=False),
        sa.Column("supplier_type", sa.String(32), nullable=False),
        sa.Column("country", sa.String(100)),
        sa.Column("email_id", sa.String(255)),
    )
    op.create_table(
        "erp_lead",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_name", sa.String(200), nullable=False),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("company_name", sa.String(200)),
        sa.Column("email_id", sa.String(255)),
        sa.Column("mobile_no", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(100)),
        sa.Column("customer_id", sa.Uuid()),
    )
    op.create_table(
        "erp_opportunity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opportunity_from", sa.String(32), nullable=False),
        sa.Column("party_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sales_stage", sa.String(64), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("lead_id", sa.Uuid()),
    )
    op.create_table(
        "erp_issue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("issue_type", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("agreement_status", sa.String(64)),
        sa.Column("customer_id", sa.Uuid()),
        sa.Column("response_by", sa.DateTime(timezone=True)),
        sa.Column("sla_resolution_by", sa.DateTime(timezone=True)),
        sa.Column("issue_split_from", sa.Uuid()),
    )


def downgrade() -> None:
    for table in (
        "erp_issue",
        "erp_opportunity",
        "erp_lead",
        "erp_supplier",
        "erp_customer",
        "erp_item",
    ):
        op.drop_table(table)
{%- endif %}
