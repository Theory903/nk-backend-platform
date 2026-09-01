{%- if cookiecutter.orm != "sqlalchemy" %}
"""Payment ledger term columns — SQLAlchemy only."""

revision = "erp_payment_terms_20260902"
down_revision = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
{%- else %}
"""Add payment_term + due_date to payment ledger for AR/AP term rows."""

import sqlalchemy as sa
from alembic import op

revision = "erp_payment_terms_20260902"
down_revision = "erp_doctype_20260902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("erp_payment_ledger", sa.Column("payment_term", sa.String(128), nullable=True))
    op.add_column("erp_payment_ledger", sa.Column("due_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("erp_payment_ledger", "due_date")
    op.drop_column("erp_payment_ledger", "payment_term")
{%- endif %}
