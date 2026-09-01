#!/usr/bin/env python3
"""Export the live FastAPI OpenAPI document for Postman / Insomnia / Bruno.

Future routes are included automatically because the schema is generated from
``get_app().openapi()`` — any router registered on the application appears in
the output without editing this script.

Also writes ``docs/postman-environment.json`` with collection variables
(baseUrl, testEmail, accessToken, …) aligned to the exported OpenAPI.

Usage::

    uv run nk export-openapi
    uv run python -m scripts.export_openapi --format both
    uv run python -m scripts.export_openapi --server http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any


def resolve_postman_defaults() -> dict[str, str]:
    """Dev defaults for Postman environment + OpenAPI examples."""
    port = os.environ.get("NK_API_PORT") or os.environ.get("PORT") or "8000"
    host = os.environ.get("NK_API_HOST", "127.0.0.1")
    protocol = os.environ.get("NK_API_PROTOCOL", "http")
    base_url = os.environ.get("NK_API_BASE_URL") or f"{protocol}://{host}:{port}"
    return {
        "baseUrl": base_url,
        "host": host,
        "port": str(port),
        "protocol": protocol,
        "testEmail": os.environ.get("NK_TEST_EMAIL", "dev@example.com"),
        "testPassword": os.environ.get("NK_TEST_PASSWORD", "DevPass123!"),
        "accessToken": "",
        "csrfToken": "",
        "verifyToken": "",
    }


def default_server_url() -> str:
    """Prefer 127.0.0.1 — OrbStack/macOS often resets ::1 for published ports."""
    return resolve_postman_defaults()["baseUrl"]


def _project_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    cwd = Path.cwd()
    if (cwd / "platform.yaml").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / "platform.yaml").exists():
            return parent
    return cwd


def _project_name(root: Path) -> str:
    manifest_path = root / "platform.yaml"
    if manifest_path.exists():
        try:
            import yaml
        except ImportError:
            yaml = None  # type: ignore[assignment]
        if yaml is not None:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            name = loaded.get("project")
            if isinstance(name, str) and name:
                return name
    for child in root.iterdir():
        if child.is_dir() and (child / "web" / "application.py").exists():
            return child.name
    raise RuntimeError("could not resolve project package name")


def enhance_for_postman(
    schema: dict[str, Any],
    defaults: dict[str, str],
) -> dict[str, Any]:
    """Patch OpenAPI so Postman imports variables, auth, and examples correctly."""
    enhanced = copy.deepcopy(schema)

    enhanced["servers"] = [
        {
            "url": "{baseUrl}",
            "description": (
                "Local API. Import docs/postman-environment.json, select "
                "NK Local Dev, then import this OpenAPI file."
            ),
            "variables": {
                "baseUrl": {
                    "default": defaults["baseUrl"],
                    "description": "Full base URL (http://127.0.0.1:8000 on macOS/OrbStack)",
                },
            },
        },
    ]

    components = enhanced.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})

    oauth = schemes.get("OAuth2PasswordBearer")
    if isinstance(oauth, dict):
        flows = oauth.setdefault("flows", {})
        password = flows.setdefault("password", {})
        password["tokenUrl"] = "/api/auth/jwt/login"
        oauth["description"] = (
            "JWT password flow. POST x-www-form-urlencoded to tokenUrl with "
            "username=<email> and password=<password>. The field name is "
            "username, not email."
        )

    if "HTTPBearer" not in schemes:
        schemes["HTTPBearer"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Set Authorization: Bearer {{'{{'}}accessToken{{'}}'}} after "
                "/api/auth/jwt/login."
            ),
        }

    paths = enhanced.get("paths", {})
    _enhance_register(paths, defaults)
    _enhance_jwt_login(paths, defaults)
    _enhance_verify_flow(paths, defaults)
    _enhance_login_schemas(components.get("schemas", {}), defaults)

    info = enhanced.setdefault("info", {})
    postman_note = (
        "Postman: import docs/postman-environment.json, then this file. "
        "Run Register → JWT Login (form body, username=email). "
        "For verify: Request Verify Token, copy token from api logs (dev), "
        "POST /api/auth/verify with verifyToken."
    )
    existing = info.get("description") or ""
    if postman_note not in existing:
        info["description"] = f"{existing.rstrip()}\n\n{postman_note}".strip()

    enhanced["x-postman"] = {
        "environment": "docs/postman-environment.json",
        "variables": sorted(defaults.keys()),
        "importOrder": [
            "Import docs/postman-environment.json into Postman Environments",
            "Import docs/openapi.json into Postman Collections",
            "Select the NK Local Dev environment",
            "POST /api/auth/register, then POST /api/auth/jwt/login",
            "Optional verify: request-verify-token → copy token from api logs → verify",
            "Set accessToken from login response for protected routes",
        ],
    }
    return enhanced


def _enhance_register(paths: dict[str, Any], defaults: dict[str, str]) -> None:
    register = paths.get("/api/auth/register", {}).get("post")
    if not isinstance(register, dict):
        return
    content = register.setdefault("requestBody", {}).setdefault("content", {})
    json_body = content.setdefault("application/json", {})
    json_body["examples"] = {
        "dev-register": {
            "summary": "Register the dev test user",
            "value": {
                "email": defaults["testEmail"],
                "password": defaults["testPassword"],
            },
        },
    }


def _enhance_jwt_login(paths: dict[str, Any], defaults: dict[str, str]) -> None:
    login = paths.get("/api/auth/jwt/login", {}).get("post")
    if not isinstance(login, dict):
        return
    login["description"] = (
        "OAuth2 password login. Body must be **application/x-www-form-urlencoded** "
        "(not JSON). Use field `username` for the email address."
    )
    content = login.setdefault("requestBody", {}).setdefault("content", {})
    form = content.setdefault("application/x-www-form-urlencoded", {})
    form["examples"] = {
        "dev-login": {
            "summary": "Login with dev credentials (username is the email)",
            "value": {
                "username": defaults["testEmail"],
                "password": defaults["testPassword"],
            },
        },
    }


def _enhance_verify_flow(paths: dict[str, Any], defaults: dict[str, str]) -> None:
    request_verify = paths.get("/api/auth/request-verify-token", {}).get("post")
    if isinstance(request_verify, dict):
        request_verify["description"] = (
            "Request a verification email. In dev (no SMTP), the token is logged "
            "by the API — run `docker logs alpha-api-1 | rg verification token`."
        )
        content = request_verify.setdefault("requestBody", {}).setdefault("content", {})
        json_body = content.setdefault("application/json", {})
        json_body["examples"] = {
            "dev-request-verify": {
                "summary": "Request verify token for the dev test user",
                "value": {"email": defaults["testEmail"]},
            },
        }

    verify = paths.get("/api/auth/verify", {}).get("post")
    if isinstance(verify, dict):
        verify["description"] = (
            "Confirm email with the signed token from request-verify-token. "
            "Do not use the placeholder `string` — paste the real token from "
            "dev api logs into the verifyToken environment variable."
        )
        content = verify.setdefault("requestBody", {}).setdefault("content", {})
        json_body = content.setdefault("application/json", {})
        json_body["examples"] = {
            "dev-verify": {
                "summary": "Verify using token from dev api logs",
                "value": {"token": "{{'{{'}}verifyToken{{'}}'}}"},
            },
        }


def _enhance_login_schemas(
    schemas: dict[str, Any],
    defaults: dict[str, str],
) -> None:
    for name, body in schemas.items():
        if not isinstance(body, dict) or "jwt_login" not in name:
            continue
        props = body.setdefault("properties", {})
        username = props.get("username")
        if isinstance(username, dict):
            username["description"] = (
                "Email address (OAuth2 password flow uses the field name username)"
            )
            username["example"] = defaults["testEmail"]
        password = props.get("password")
        if isinstance(password, dict):
            password["example"] = defaults["testPassword"]
        if "verify_verify" in name:
            token = props.get("token")
            if isinstance(token, dict):
                token["description"] = (
                    "Signed verification token from request-verify-token "
                    "(dev: copy from api logs; not the JWT access_token)"
                )
                token["example"] = "{{'{{'}}verifyToken{{'}}'}}"


def write_postman_environment(defaults: dict[str, str], output: Path) -> Path:
    """Write a Postman environment aligned with OpenAPI server variables."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {
        "name": "NK Local Dev",
        "values": [
            {
                "key": key,
                "value": value,
                "type": "secret" if key in {"testPassword", "accessToken"} else "default",
                "enabled": True,
            }
            for key, value in defaults.items()
        ],
        "_postman_variable_scope": "environment",
        "_postman_exported_at": "auto-generated-by-nk-export-openapi",
    }
    output.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def build_openapi_schema(
    root: Path,
    *,
    servers: list[str] | None = None,
    postman: bool = True,
) -> dict[str, Any]:
    """Build OpenAPI from the application factory (no HTTP server required)."""
    project = _project_name(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    application = import_module(f"{project}.web.application")
    app = application.get_app()
    schema = app.openapi()
    defaults = resolve_postman_defaults()
    if servers:
        schema["servers"] = [{"url": url} for url in servers]
    elif postman:
        schema = enhance_for_postman(schema, defaults)
    elif not schema.get("servers"):
        schema["servers"] = [{"url": default_server_url()}]
    return schema


def write_openapi(
    schema: dict[str, Any],
    output: Path,
    *,
    fmt: str = "json",
) -> list[Path]:
    """Write OpenAPI to disk. ``fmt`` is json, yaml, or both."""
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if fmt in {"json", "both"}:
        json_path = output if output.suffix.lower() == ".json" else output.with_suffix(".json")
        json_path.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(json_path)

    if fmt in {"yaml", "both"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyYAML is required for --format yaml/both") from exc
        yaml_path = (
            output
            if output.suffix.lower() in {".yaml", ".yml"}
            else output.with_suffix(".yaml")
        )
        if fmt == "both" and output.suffix.lower() == ".json":
            yaml_path = output.with_suffix(".yaml")
        yaml_path.write_text(
            yaml.safe_dump(schema, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        written.append(yaml_path)

    return written


def export_openapi(
    *,
    project_root: Path | None = None,
    output: Path | None = None,
    fmt: str = "json",
    servers: list[str] | None = None,
    postman: bool = True,
) -> tuple[list[Path], dict[str, Any]]:
    root = _project_root(project_root)
    target = output or (root / "docs" / "openapi.json")
    schema = build_openapi_schema(root, servers=servers, postman=postman)
    written = write_openapi(schema, target, fmt=fmt)
    if postman and not servers:
        env_path = write_postman_environment(
            resolve_postman_defaults(),
            root / "docs" / "postman-environment.json",
        )
        written.append(env_path)
    return written, schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export OpenAPI from get_app().openapi() for Postman, Insomnia, "
            "Bruno, or Hoppscotch import. New routes appear automatically."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: docs/openapi.json)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "yaml", "both"),
        default="json",
        dest="fmt",
        help="Serialization format (default: json)",
    )
    parser.add_argument(
        "--server",
        action="append",
        default=[],
        metavar="URL",
        help="OpenAPI servers[].url entry (repeatable; skips Postman enhancements)",
    )
    parser.add_argument(
        "--no-postman",
        action="store_true",
        help="Skip Postman variable/examples/environment enhancements",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Generated project root (default: discover via platform.yaml)",
    )
    args = parser.parse_args(argv)

    root = _project_root(args.project_root)
    try:
        written, schema = export_openapi(
            project_root=root,
            output=args.output,
            fmt=args.fmt,
            servers=args.server or None,
            postman=not args.no_postman and not args.server,
        )
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"export-openapi failed: {exc}", file=sys.stderr)
        return 1

    paths = schema.get("paths") or {}
    for path in written:
        display = path.relative_to(root) if path.is_relative_to(root) else path
        print(f"wrote {display}")
    print(f"paths: {len(paths)}")
    if not args.no_postman and not args.server:
        print(
            "Postman: import docs/postman-environment.json → Environments, "
            "then docs/openapi.json → Collections",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
