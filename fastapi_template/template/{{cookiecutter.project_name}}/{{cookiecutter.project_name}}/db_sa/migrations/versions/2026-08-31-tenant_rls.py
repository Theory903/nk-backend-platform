{%- if cookiecutter.db_info.name != "postgresql" %}
"""Tenant RLS is only available for PostgreSQL profiles."""

import sqlalchemy as sa
from alembic import op

revision = "tenant_rls_20260831"
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
down_revision = "8caca4abd7b4"
{%- elif cookiecutter.add_dummy in [True, "True", "true", 1, "1"] %}
down_revision = "2b7380507a71"
{%- else %}
down_revision = "819cbf6e030b"
{%- endif %}
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable auth tables; row-level isolation is PostgreSQL-only."""
    _create_auth_tables()


def downgrade() -> None:
    """Remove durable auth tables."""
    _drop_auth_tables()


def _create_auth_tables() -> None:
    op.create_table(
        "auth_session",
        sa.Column("session_id", sa.String(128), primary_key=True),
        sa.Column("principal_id", sa.String(255), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("last_activity", sa.Float, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
        sa.Column("idle_expires_at", sa.Float, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rotated_from", sa.String(128)),
        sa.Column("rotated_to", sa.String(128)),
        sa.Column("revoked_at", sa.Float),
        sa.Column("revoked_reason", sa.String(64)),
        sa.Column("user_agent", sa.String(1024), nullable=False),
        sa.Column("ip_address", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "auth_api_key",
        sa.Column("key_id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("digest", sa.String(128), nullable=False, unique=True),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(255)),
        sa.Column("org_id", sa.String(255)),
        sa.Column("scopes", sa.JSON, nullable=False),
        sa.Column("ip_allowlist", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", sa.JSON, nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "auth_membership",
        sa.Column("user_id", sa.String(255), primary_key=True),
        sa.Column("org_id", sa.String(255), primary_key=True),
        sa.Column("roles", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "auth_access_token",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )


def _drop_auth_tables() -> None:
    for table_name in (
        "auth_access_token",
        "auth_membership",
        "auth_api_key",
        "auth_session",
    ):
        op.drop_table(table_name, if_exists=True)

{%- else %}
"""Enable tenant isolation for every application table carrying org_id."""

import os

import sqlalchemy as sa
from alembic import op

revision = "tenant_rls_20260831"
{%- if cookiecutter.add_users in [True, "True", "true", 1, "1"] %}
down_revision = "8caca4abd7b4"
{%- elif cookiecutter.add_dummy in [True, "True", "true", 1, "1"] %}
down_revision = "2b7380507a71"
{%- else %}
down_revision = "819cbf6e030b"
{%- endif %}
branch_labels = None
depends_on = None


def _create_auth_tables() -> None:
    op.create_table(
        "auth_session",
        sa.Column("session_id", sa.String(128), primary_key=True),
        sa.Column("principal_id", sa.String(255), nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("last_activity", sa.Float, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
        sa.Column("idle_expires_at", sa.Float, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rotated_from", sa.String(128)),
        sa.Column("rotated_to", sa.String(128)),
        sa.Column("revoked_at", sa.Float),
        sa.Column("revoked_reason", sa.String(64)),
        sa.Column("user_agent", sa.String(1024), nullable=False),
        sa.Column("ip_address", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "auth_api_key",
        sa.Column("key_id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("digest", sa.String(128), nullable=False, unique=True),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(255)),
        sa.Column("org_id", sa.String(255)),
        sa.Column("scopes", sa.JSON, nullable=False),
        sa.Column("ip_allowlist", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", sa.JSON, nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "auth_membership",
        sa.Column("user_id", sa.String(255), primary_key=True),
        sa.Column("org_id", sa.String(255), primary_key=True),
        sa.Column("roles", sa.JSON, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "auth_access_token",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )


def _drop_auth_tables() -> None:
    for table_name in (
        "auth_access_token",
        "auth_membership",
        "auth_api_key",
        "auth_session",
    ):
        op.drop_table(table_name, if_exists=True)


def upgrade() -> None:
    _create_auth_tables()
    owner_role = os.getenv("{{cookiecutter.project_name | upper}}_DB_OWNER_ROLE")
    if owner_role:
        quoted_owner = '"' + owner_role.replace('"', '""') + '"'
        op.execute(
            f"""
            DO $$
            DECLARE table_name text;
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{owner_role.replace("'", "''")}') THEN
                RETURN;
              END IF;
              FOR table_name IN
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
              LOOP
                EXECUTE format(
                  'ALTER TABLE public.%I OWNER TO {quoted_owner}',
                  table_name
                );
              END LOOP;
            END $$;
            """,
        )
    op.execute(
        """
        DO $$
        DECLARE table_name text;
        BEGIN
          FOR table_name IN
            SELECT c.table_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.column_name = 'org_id'
              AND c.table_name NOT LIKE 'auth_%'
          LOOP
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
            EXECUTE format(
              'CREATE POLICY nk_tenant_isolation ON %I USING (org_id::text = current_setting(''app.tenant_id'', true)) WITH CHECK (org_id::text = current_setting(''app.tenant_id'', true))',
              table_name
            );
          END LOOP;
        END $$;
        """,
    )
def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE table_name text;
        BEGIN
          FOR table_name IN
            SELECT c.table_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.column_name = 'org_id'
              AND c.table_name NOT LIKE 'auth_%'
          LOOP
            EXECUTE format('DROP POLICY IF EXISTS nk_tenant_isolation ON %I', table_name);
            EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', table_name);
            EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', table_name);
          END LOOP;
        END $$;
        """,
    )
    _drop_auth_tables()
{%- endif %}
