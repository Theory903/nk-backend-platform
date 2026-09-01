"""Create a PostgreSQL backup and a secret-free restore manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
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


def create_backup(destination: Path) -> Path:
    """Run pg_dump using DATABASE_URL without printing credentials."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured")
    env = _postgres_env(database_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(destination)],
        env=env,
        check=True,
    )
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = destination.with_suffix(destination.suffix + ".json")
    manifest.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "backup": destination.name,
                "sha256": digest,
                "format": "postgresql-custom",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"wrote backup manifest: {create_backup(args.destination)}")


if __name__ == "__main__":
    main()
