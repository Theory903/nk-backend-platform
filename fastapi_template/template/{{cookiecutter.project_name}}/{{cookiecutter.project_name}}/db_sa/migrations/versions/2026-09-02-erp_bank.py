{%- if cookiecutter.orm != "sqlalchemy" %}
"""ERP bank transaction table — SQLAlchemy only."""

revision = "erp_bank_20260902"
down_revision = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
{%- else %}
"""Bank transaction table for reconciliation."""

import sqlalchemy as sa
from alembic import op

revision = "erp_bank_20260902"
down_revision = "erp_parity_20260902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_bank_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bank_account", sa.String(128), nullable=False, index=True),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("deposit", sa.Float(), nullable=False, server_default="0"),
        sa.Column("withdrawal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reference", sa.String(128)),
        sa.Column("is_reconciled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("matched_voucher_type", sa.String(64)),
        sa.Column("matched_voucher_id", sa.Uuid()),
    )


def downgrade() -> None:
    op.drop_table("erp_bank_transaction")
{%- endif %}
