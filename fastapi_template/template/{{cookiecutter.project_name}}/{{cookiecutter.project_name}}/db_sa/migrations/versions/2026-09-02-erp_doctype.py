{%- if cookiecutter.orm != "sqlalchemy" %}
"""Universal doctype record table — SQLAlchemy only."""

revision = "erp_doctype_20260902"
down_revision = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
{%- else %}
"""Universal ERPNext DocType JSON store."""

import sqlalchemy as sa
from alembic import op

revision = "erp_doctype_20260902"
down_revision = "erp_bank_20260902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_doctype_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("doctype", sa.String(128), nullable=False, index=True),
        sa.Column("docname", sa.String(128), nullable=False, index=True),
        sa.Column("docstatus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_submittable", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("module", sa.String(64)),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_erp_doctype_record_org_doctype_docname",
        "erp_doctype_record",
        ["org_id", "doctype", "docname"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_erp_doctype_record_org_doctype_docname", table_name="erp_doctype_record")
    op.drop_table("erp_doctype_record")
{%- endif %}
