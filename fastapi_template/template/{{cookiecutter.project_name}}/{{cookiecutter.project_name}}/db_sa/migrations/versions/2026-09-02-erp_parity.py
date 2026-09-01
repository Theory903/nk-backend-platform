{%- if cookiecutter.orm != "sqlalchemy" %}
"""ERP parity lifecycle columns — SQLAlchemy only."""

revision = "erp_parity_20260902"
down_revision = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
{%- else %}
"""Submit / cancel / amend lifecycle columns on erp_document."""

import sqlalchemy as sa
from alembic import op

revision = "erp_parity_20260902"
down_revision = "erp_txn_20260901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("erp_document", sa.Column("docstatus", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("erp_document", sa.Column("per_delivered", sa.Float(), nullable=False, server_default="0"))
    op.add_column("erp_document", sa.Column("per_billed", sa.Float(), nullable=False, server_default="0"))
    op.add_column("erp_document", sa.Column("amended_from", sa.Uuid(), nullable=True))
    op.add_column("erp_document", sa.Column("company", sa.String(128), nullable=False, server_default="NK Default"))
    op.add_column("erp_document", sa.Column("currency", sa.String(8), nullable=False, server_default="USD"))


def downgrade() -> None:
    op.drop_column("erp_document", "currency")
    op.drop_column("erp_document", "company")
    op.drop_column("erp_document", "amended_from")
    op.drop_column("erp_document", "per_billed")
    op.drop_column("erp_document", "per_delivered")
    op.drop_column("erp_document", "docstatus")
{%- endif %}
