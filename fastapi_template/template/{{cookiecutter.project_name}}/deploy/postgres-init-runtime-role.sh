#!/bin/sh
set -eu

: "${POSTGRES_RUNTIME_USER:?POSTGRES_RUNTIME_USER is required}"
: "${POSTGRES_RUNTIME_PASSWORD:?POSTGRES_RUNTIME_PASSWORD is required}"
: "${POSTGRES_OWNER_ROLE:?POSTGRES_OWNER_ROLE is required}"

if [ "$POSTGRES_RUNTIME_USER" = "$POSTGRES_USER" ] ||
   [ "$POSTGRES_OWNER_ROLE" = "$POSTGRES_USER" ] ||
   [ "$POSTGRES_RUNTIME_USER" = "$POSTGRES_OWNER_ROLE" ]; then
    echo "admin, owner, and runtime PostgreSQL roles must be distinct" >&2
    exit 1
fi

escape_sql_literal() {
    printf "%s" "$1" | sed "s/'/''/g"
}

OWNER_ROLE=$(escape_sql_literal "$POSTGRES_OWNER_ROLE")
RUNTIME_USER=$(escape_sql_literal "$POSTGRES_RUNTIME_USER")
RUNTIME_PASSWORD=$(escape_sql_literal "$POSTGRES_RUNTIME_PASSWORD")
DATABASE_NAME=$(escape_sql_literal "$POSTGRES_DB")

psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 \
    <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${OWNER_ROLE}') THEN
        EXECUTE format(
            'CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS',
            '${OWNER_ROLE}'
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS',
            '${OWNER_ROLE}'
        );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${RUNTIME_USER}') THEN
        EXECUTE format(
            'CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L',
            '${RUNTIME_USER}',
            '${RUNTIME_PASSWORD}'
        );
    ELSE
        EXECUTE format(
            'ALTER ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L',
            '${RUNTIME_USER}',
            '${RUNTIME_PASSWORD}'
        );
    END IF;
END
\$\$;

GRANT CONNECT ON DATABASE "${DATABASE_NAME}" TO "${RUNTIME_USER}";
GRANT USAGE ON SCHEMA public TO "${RUNTIME_USER}";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "${RUNTIME_USER}";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "${RUNTIME_USER}";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "${RUNTIME_USER}";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "${RUNTIME_USER}";
SQL
