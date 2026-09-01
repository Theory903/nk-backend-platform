"""Add payment term master tables — SQLAlchemy only."""

revision = "erp_payment_terms_masters_20260902"
down_revision = "erp_payment_terms_20260902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op

    op.create_table(
        "erp_payment_term",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_term_name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("invoice_portion", sa.Float(), nullable=False),
        sa.Column("mode_of_payment", sa.String(64), nullable=True),
        sa.Column("due_date_based_on", sa.String(64), nullable=True),
        sa.Column("credit_days", sa.Integer(), nullable=False),
        sa.Column("credit_months", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_erp_payment_term_org_id", "erp_payment_term", ["org_id"], unique=False)
    op.create_index(
        "ix_erp_payment_term_payment_term_name",
        "erp_payment_term",
        ["payment_term_name"],
        unique=False,
    )

    op.create_table(
        "erp_payment_terms_template",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("template_name", sa.String(128), nullable=False),
        sa.Column(
            "allocate_payment_based_on_payment_terms",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_erp_payment_terms_template_org_id",
        "erp_payment_terms_template",
        ["org_id"],
        unique=False,
    )
    op.create_index(
        "ix_erp_payment_terms_template_template_name",
        "erp_payment_terms_template",
        ["template_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("erp_payment_terms_template")
    op.drop_table("erp_payment_term")
