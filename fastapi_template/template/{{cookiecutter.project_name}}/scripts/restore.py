"""Restore a PostgreSQL backup after an explicit operator confirmation."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse


def _postgres_env(database_url: str) -> dict[str, str]:
    """Translate the URL into libpq environment variables, never argv."""
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    env = os.environ.copy()
    env.update(
        {
            "PGHOST": parsed.hostname,
            "PGPORT": str(parsed.port or 5432),
            "PGDATABASE": parsed.path.lstrip("/"),
        },
    )
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    env.pop("DATABASE_URL", None)
    return env


def restore_backup(source: Path, *, confirm: bool) -> None:
    """Restore a custom-format dump; never run destructive work implicitly."""
    if not confirm:
        raise RuntimeError("restore requires --confirm")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured")
    env = _postgres_env(database_url)
    if not source.is_file():
        raise FileNotFoundError(source)
    subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--dbname",
            env["PGDATABASE"],
            str(source),
        ],
        env=env,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="confirm destructive replacement of matching database objects",
    )
    args = parser.parse_args()
    restore_backup(args.source, confirm=args.confirm)
    print(f"restored backup: {args.source}")


if __name__ == "__main__":
    main()
