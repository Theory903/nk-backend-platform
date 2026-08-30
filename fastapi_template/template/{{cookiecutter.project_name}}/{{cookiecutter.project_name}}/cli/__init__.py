"""NK app CLI — Next.js-style verbs for a generated project.

Commands: doctor, validate, check, dev, build, generate
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "platform.yaml").exists():
        return cwd
    # Allow running from package subdirs
    for parent in cwd.parents:
        if (parent / "platform.yaml").exists():
            return parent
    return cwd


def _load_manifest(root: Path) -> dict:
    path = root / "platform.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def needs_compose(root: Path | None = None) -> bool:
    """True when platform needs Docker Compose infra (db/redis/brokers)."""
    root = root or _project_root()
    manifest = _load_manifest(root)
    providers = manifest.get("providers") or {}
    modules = manifest.get("modules") or {}
    db = providers.get("database")
    if db not in (None, "none", False, "False"):
        return True
    for key in ("redis", "rabbitmq", "kafka", "nats", "taskiq"):
        if modules.get(key) in (True, "True", "true", 1):
            return True
    return False


def _run(cmd: Sequence[str], *, cwd: Path | None = None) -> int:
    print("+", " ".join(cmd))
    return subprocess.call(list(cmd), cwd=str(cwd or _project_root()))


def cmd_doctor(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.doctor import run_doctor

    ok = run_doctor(root)
    return 0 if ok else 1


def cmd_validate(_: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.validate import run_validate

    ok = run_validate(root)
    return 0 if ok else 1


def cmd_check(_: argparse.Namespace) -> int:
    root = _project_root()
    pkg = None
    for child in root.iterdir():
        if child.is_dir() and (child / "__init__.py").exists() and child.name not in {
            "tests",
            "scripts",
            "business",
            "deploy",
        }:
            # prefer directory matching project name from platform.yaml
            pkg = child
            break
    manifest = _load_manifest(root)
    project = manifest.get("project")
    if project and (root / project).is_dir():
        pkg = root / project
    pkg_name = pkg.name if pkg else "."

    steps = [
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "mypy", pkg_name, "tests"],
        ["uv", "run", "pytest", "-q"],
    ]
    for step in steps:
        code = _run(step, cwd=root)
        if code != 0:
            print(f"nk check failed at: {' '.join(step)}", file=sys.stderr)
            print("Fix: re-run that command, then `uv run nk check`", file=sys.stderr)
            return code
    print("nk check: all green")
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    root = _project_root()
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    if getattr(args, "app_only", False):
        os.environ.setdefault(f"{project.upper()}_ENVIRONMENT", "dev")
    host = os.environ.get("HOST", "0.0.0.0")
    port = os.environ.get("PORT", "8000")

    if needs_compose(root) and not getattr(args, "app_only", False):
        if shutil.which("docker") is None:
            print(
                "Docker is required for this profile. "
                "Install Docker or pass --app-only for uvicorn only.",
                file=sys.stderr,
            )
            return 1
        compose = [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.dev.yml",
            "up",
            "--build",
        ]
        print(f"Docs will be at http://localhost:{port}/api/docs")
        return _run(compose, cwd=root)

    # minimal / no-infra: uvicorn reload only
    app = f"{project}.web.application:get_app"
    cmd = [
        "uv",
        "run",
        "uvicorn",
        app,
        "--factory",
        "--reload",
        "--host",
        host,
        "--port",
        str(port),
    ]
    print(f"Starting {app}")
    print(f"Open http://localhost:{port}/api/docs")
    return _run(cmd, cwd=root)


def cmd_build(_: argparse.Namespace) -> int:
    root = _project_root()
    if shutil.which("docker") is None:
        print("Docker is required for `nk build`.", file=sys.stderr)
        return 1
    tag = (_load_manifest(root).get("project") or root.name) + ":local"
    return _run(
        ["docker", "build", "--target", "prod", "--tag", tag, "."],
        cwd=root,
    )


def cmd_generate(args: argparse.Namespace) -> int:
    root = _project_root()
    sys.path.insert(0, str(root))
    from scripts.generate_module import generate_module

    fields = []
    for item in args.fields or []:
        if ":" not in item:
            print(f"invalid field {item!r}; use name:type", file=sys.stderr)
            return 2
        name, ftype = item.split(":", 1)
        fields.append((name, ftype))
    created = generate_module(
        args.module,
        fields=fields or None,
        project_root=root,
    )
    for path in created:
        print(f"created {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nk",
        description="NK Backend OS — Next.js-style project CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Environment health checks")
    p_doctor.set_defaults(func=cmd_doctor)

    p_validate = sub.add_parser("validate", help="Validate project structure")
    p_validate.set_defaults(func=cmd_validate)

    p_check = sub.add_parser("check", help="format + lint + types + tests")
    p_check.set_defaults(func=cmd_check)

    p_dev = sub.add_parser("dev", help="Run local app (compose or uvicorn)")
    p_dev.add_argument(
        "--app-only",
        action="store_true",
        help="Force uvicorn only (skip Docker Compose)",
    )
    p_dev.set_defaults(func=cmd_dev)

    p_build = sub.add_parser("build", help="Build production Docker image")
    p_build.set_defaults(func=cmd_build)

    p_gen = sub.add_parser("generate", help="Scaffold a business module")
    p_gen.add_argument("module", help="dotted path, e.g. crm.leads")
    p_gen.add_argument(
        "--fields",
        nargs="*",
        default=[],
        help="field specs name:type",
    )
    p_gen.set_defaults(func=cmd_generate)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    code = int(args.func(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
