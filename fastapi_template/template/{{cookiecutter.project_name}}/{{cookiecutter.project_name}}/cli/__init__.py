"""NK app CLI — Next.js-style verbs for a generated project.

Commands: doctor, validate, check, dev, build, start, migrate, seed,
generate, eval, jobs replay, deploy, scale-status
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from collections.abc import Sequence


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


def _select_port(
    env_name: str,
    preferred: int,
    *,
    reserved: set[int] | None = None,
) -> int:
    """Use an explicit port or select the next available local port."""
    reserved = reserved or set()
    configured = os.environ.get(env_name)
    if configured is not None:
        try:
            port = int(configured)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be an integer port") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{env_name} must be between 1 and 65535")
        if port in reserved:
            raise ValueError(f"{env_name} conflicts with another development port")
        if not _port_is_available(port):
            raise ValueError(
                f"{env_name}={port} is already in use; choose another port"
            )
        return port

    port = preferred
    while port <= 65535:
        if port in reserved:
            port += 1
            continue
        if _port_is_available(port):
            os.environ[env_name] = str(port)
            return port
        port += 1

    raise ValueError(f"no available port found for {env_name}")


def _port_is_available(port: int) -> bool:
    """Return whether a TCP listener can be bound to the local port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _load_dotenv_port_overrides(project: str) -> None:
    """Load port-related values from ``.env`` without overriding the shell."""
    env_file = _project_root() / ".env"
    if not env_file.exists():
        return

    names = {
        "COMPOSE_PROJECT_NAME",
        "GRAFANA_PORT",
        "PORT",
        f"{project.upper()}_PORT",
    }
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if (
            separator
            and (key in names or key.startswith("NK_"))
            and key not in os.environ
        ):
            os.environ[key] = value.strip().strip("\"'")


def _dotenv_has_key(root: Path, key_name: str) -> bool:
    """Check whether a key exists in ``.env`` without exposing its value."""
    env_file = root / ".env"
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if line.partition("=")[0].strip() == key_name:
            return True
    return False


def _project_port(project: str) -> int:
    """Read the generated app's preferred port from environment."""
    env_name = f"{project.upper()}_PORT"
    configured = os.environ.get(env_name)
    if not configured:
        return 8000
    try:
        port = int(configured)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer port") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{env_name} must be between 1 and 65535")
    return port


def _select_api_port(project: str) -> int:
    """Resolve the API host port, preferring the Compose-specific override."""
    _load_dotenv_port_overrides(project)
    project_port = _project_port(project)
    if "NK_API_PORT" in os.environ:
        return _select_port("NK_API_PORT", project_port)

    port = _select_port("PORT", project_port)
    os.environ["NK_API_PORT"] = str(port)
    return port


def _configure_dev_ports(manifest: dict, *, otlp: bool = False) -> int:
    """Configure collision-free host ports for local development."""
    project = manifest.get("project") or _project_root().name
    api_port = _select_api_port(project)
    selected_ports = {api_port}

    providers = manifest.get("providers") or {}
    database = providers.get("database")
    database_ports = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    if database in database_ports:
        db_port = _select_port(
            "NK_DB_PORT",
            database_ports[database],
            reserved=selected_ports,
        )
        selected_ports.add(db_port)

    modules = manifest.get("modules") or {}
    service_ports = {
        "redis": ("redis", 6379),
        "rabbitmq": ("rabbit", 5672),
        "kafka": ("kafka", 9094),
        "nats": ("nats", 4222),
    }
    for module, (env_name, preferred) in service_ports.items():
        if modules.get(module) in (True, "True", "true", 1):
            service_port = _select_port(
                f"NK_{env_name.upper()}_PORT",
                preferred,
                reserved=selected_ports,
            )
            selected_ports.add(service_port)
            if module == "rabbitmq":
                management_port = _select_port(
                    "NK_RABBIT_MANAGEMENT_PORT",
                    15672,
                    reserved=selected_ports,
                )
                selected_ports.add(management_port)

    if otlp:
        if "NK_GRAFANA_PORT" not in os.environ and "GRAFANA_PORT" in os.environ:
            os.environ["NK_GRAFANA_PORT"] = os.environ["GRAFANA_PORT"]
        _select_port("NK_GRAFANA_PORT", 3000, reserved=selected_ports)

    return int(os.environ["NK_API_PORT"])


def _compose_command(
    project_name: str,
    *args: str,
    otlp: bool = False,
) -> list[str]:
    """Build a Compose command scoped to one isolated project name."""
    command = [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.dev.yml",
    ]
    if otlp:
        command.extend(["-f", "deploy/docker-compose.otlp.yml"])
    command.extend(args)
    return command


def _compose_has_containers(root: Path, project_name: str) -> bool:
    """Return whether Compose already has containers for this project."""
    result = subprocess.run(
        _compose_command(project_name, "ps", "-aq"),
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _compose_project_is_used(root: Path, project_name: str) -> bool:
    """Return whether containers or persistent Compose resources use a name."""
    if _compose_has_containers(root, project_name):
        return True
    label = f"com.docker.compose.project={project_name}"
    for resource in ("volume", "network"):
        result = subprocess.run(
            ["docker", resource, "ls", "--filter", f"label={label}", "-q"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    return False


def _compose_api_port(
    root: Path,
    project_name: str,
    container_port: int = 8000,
) -> int | None:
    """Read the host port assigned to an existing API container."""
    result = subprocess.run(
        _compose_command(project_name, "port", "api", str(container_port)),
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    endpoint = result.stdout.strip().splitlines()
    if endpoint:
        try:
            return int(endpoint[0].rsplit(":", 1)[-1].rstrip("]"))
        except ValueError:
            pass
    return None


def _next_compose_project_name(root: Path, project_name: str) -> str:
    """Find an unused project name for a second local stack."""
    suffix = 2
    while True:
        candidate = f"{project_name}-{suffix}"
        if not _compose_project_is_used(root, candidate):
            return candidate
        suffix += 1


def _choose_compose_project(
    root: Path,
    manifest: dict,
    args: argparse.Namespace,
) -> tuple[str, bool]:
    """Choose whether to reuse the current stack or create an isolated one."""
    project = manifest.get("project") or root.name
    _load_dotenv_port_overrides(project)
    project_name = os.environ.get("COMPOSE_PROJECT_NAME") or project
    if getattr(args, "new_stack", False):
        return _next_compose_project_name(root, project_name), False
    project_is_used = _compose_project_is_used(root, project_name)
    if getattr(args, "reuse", False) and not project_is_used:
        raise ValueError(
            f"Compose project '{project_name}' does not exist; "
            "remove --reuse or use --new."
        )
    if not project_is_used:
        return project_name, False

    if getattr(args, "reuse", False):
        return project_name, True

    try:
        answer = input(
            f"Compose project '{project_name}' already exists. "
            "Use existing containers? [Y/n] "
        )
    except EOFError:
        answer = ""
    if answer.strip().lower() not in {"n", "no"}:
        return project_name, True
    return _next_compose_project_name(root, project_name), False


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
    compose_mode = (
        (
            needs_compose(root)
            or getattr(args, "otlp", False)
            or getattr(args, "reuse", False)
            or getattr(args, "new_stack", False)
        )
        and not getattr(args, "app_only", False)
    )
    if compose_mode:
        if shutil.which("docker") is None:
            print(
                "Docker is required for this profile. "
                "Install Docker or pass --app-only for uvicorn only.",
                file=sys.stderr,
            )
            return 1
        if getattr(args, "otlp", False) and not (
            root / "deploy" / "docker-compose.otlp.yml"
        ).exists():
            print(
                "The OpenTelemetry overlay is not enabled in this project.",
                file=sys.stderr,
            )
            return 2
        if getattr(args, "otlp", False) and not (
            os.environ.get("GRAFANA_ADMIN_PASSWORD")
            or _dotenv_has_key(root, "GRAFANA_ADMIN_PASSWORD")
        ):
            print(
                "Set GRAFANA_ADMIN_PASSWORD in the environment or .env "
                "before using --otlp.",
                file=sys.stderr,
            )
            return 2
        try:
            compose_project, reuse_existing = _choose_compose_project(root, manifest, args)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        os.environ["COMPOSE_PROJECT_NAME"] = compose_project
        if compose_project != project:
            os.environ.setdefault(
                f"{project.upper()}_TRAEFIK_HOST",
                f"{compose_project}.localhost",
            )
        if reuse_existing:
            if getattr(args, "otlp", False):
                print(
                    "Cannot add the OpenTelemetry overlay while reusing "
                    "existing containers; use --new instead.",
                    file=sys.stderr,
                )
                return 2
            try:
                port = _compose_api_port(
                    root,
                    compose_project,
                    8000,
                )
            except ValueError as exc:
                print(f"Invalid development port: {exc}", file=sys.stderr)
                return 2
            print(f"Reusing existing Compose project '{compose_project}'.")
            if port is None:
                print("The existing stack has no host API port mapping.")
            else:
                print(f"Docs will be at http://localhost:{port}/api/docs")
            return _run(
                _compose_command(
                    compose_project,
                    "up",
                    "--no-build",
                    "--no-recreate",
                    otlp=getattr(args, "otlp", False),
                ),
                cwd=root,
            )
        try:
            port = _configure_dev_ports(manifest, otlp=getattr(args, "otlp", False))
        except ValueError as exc:
            print(f"Invalid development port: {exc}", file=sys.stderr)
            return 2
        print(
            f"Using local API port {port}; "
            "occupied service ports are shifted automatically."
        )
        compose = _compose_command(
            compose_project,
            "up",
            "--build",
            otlp=getattr(args, "otlp", False),
        )
        print(f"Docs will be at http://localhost:{port}/api/docs")
        return _run(compose, cwd=root)

    # minimal / no-infra: uvicorn reload only
    try:
        port = _select_api_port(project)
    except ValueError as exc:
        print(f"Invalid development port: {exc}", file=sys.stderr)
        return 2
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
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    _load_dotenv_port_overrides(project)
    compose_project = os.environ.get("COMPOSE_PROJECT_NAME") or project
    tags = [
        "--tag",
        f"{compose_project}-api:local",
        "--tag",
        f"{compose_project}-api:latest",
    ]
    modules = manifest.get("modules") or {}
    if modules.get("taskiq") in (True, "True", "true", 1):
        tags.extend(
            [
                "--tag",
                f"{compose_project}-worker:local",
                "--tag",
                f"{compose_project}-worker:latest",
            ]
        )
    providers = manifest.get("providers") or {}
    if (
        modules.get("migrations") in (True, "True", "true", 1)
        and providers.get("orm") != "psycopg"
    ):
        tags.extend(
            [
                "--tag",
                f"{compose_project}-migrator:local",
                "--tag",
                f"{compose_project}-migrator:latest",
            ]
        )
    return _run(
        ["docker", "build", "--target", "prod", *tags, "."],
        cwd=root,
    )


def cmd_start(args: argparse.Namespace) -> int:
    """Start the production application without autoreload."""
    root = _project_root()
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    command = [
        "uvicorn",
        f"{project}.web.application:get_app",
        "--factory",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if manifest.get("modules", {}).get("gunicorn"):
        command = [
            "gunicorn",
            "-c",
            f"{project}.gunicorn_runner",
            f"{project}.web.application:get_app",
        ]
    return _run(command, cwd=root)


def cmd_migrate(_: argparse.Namespace) -> int:
    """Apply database migrations through Alembic when enabled."""
    root = _project_root()
    if not (root / "alembic.ini").exists():
        print("No Alembic configuration is present; migrations are disabled.", file=sys.stderr)
        return 2
    return _run(["alembic", "upgrade", "head"], cwd=root)


def cmd_seed(args: argparse.Namespace) -> int:
    """Run the project seed entry point when one is provided."""
    root = _project_root()
    seed_script = root / "scripts" / "seed.py"
    if not seed_script.exists():
        print("No scripts/seed.py exists; add a seed implementation before running nk seed.", file=sys.stderr)
        return 2
    command = ["python", str(seed_script)]
    if args.name:
        command.append(args.name)
    return _run(command, cwd=root)


def cmd_eval(args: argparse.Namespace) -> int:
    """Run the generated evaluation entry point against a dataset."""
    root = _project_root()
    eval_script = root / "scripts" / "eval.py"
    if not eval_script.exists():
        print("No scripts/eval.py exists; add an evaluation runner before running nk eval.", file=sys.stderr)
        return 2
    return _run(["python", str(eval_script), args.dataset], cwd=root)


def cmd_jobs_replay(args: argparse.Namespace) -> int:
    """Replay one or more persisted dead-letter jobs."""
    root = _project_root()
    project = (_load_manifest(root).get("project") or root.name)
    return _run(
        ["python", "-m", f"{project}.jobs", "replay", *args.ids],
        cwd=root,
    )


def cmd_deploy(args: argparse.Namespace) -> int:
    """Deploy the generated Helm chart for a named environment."""
    root = _project_root()
    chart = root / "deploy" / "helm" / "nk-backend"
    if not chart.exists():
        print("Generated Helm chart is not present; deployment is unavailable.", file=sys.stderr)
        return 2
    values_name = "prod-s2" if args.environment == "prod" else args.environment
    values = root / "deploy" / "helm" / "values" / f"{values_name}.yaml"
    if not values.exists():
        print(f"Helm values file is missing: {values}", file=sys.stderr)
        return 2
    if shutil.which("helm") is None:
        print("Helm is required for nk deploy; install it or use the generated GitOps manifests.", file=sys.stderr)
        return 1
    if not args.image_digest.startswith("sha256:"):
        print(
            "An immutable --image-digest (sha256:...) is required for deployment.",
            file=sys.stderr,
        )
        return 2
    command = [
        "helm",
        "upgrade",
        "--install",
        args.release,
        str(chart),
        "--namespace",
        args.namespace,
        "--create-namespace",
        "-f",
        str(values),
        "--set",
        f"image.digest={args.image_digest}",
        "--wait",
    ]
    if args.dry_run:
        command.append("--dry-run")
    return _run(command, cwd=root)


def cmd_scale_status(_: argparse.Namespace) -> int:
    """Show the configured stage and the next scale trigger."""
    root = _project_root()
    manifest = _load_manifest(root)
    scale = manifest.get("scale") or {}
    stage = str(scale.get("stage") or "S0")
    next_stage = f"S{min(int(stage.removeprefix('S')) + 1, 6)}"
    print(f"scale stage: {stage}")
    print(f"next stage: {next_stage}")
    print("Advance only after measured SLO, saturation, and failure-recovery evidence.")
    return 0


def cmd_worker(_: argparse.Namespace) -> int:
    """Start the configured background worker."""
    root = _project_root()
    manifest = _load_manifest(root)
    project = manifest.get("project") or root.name
    if not manifest.get("modules", {}).get("taskiq"):
        print("Taskiq is not enabled in platform.yaml.", file=sys.stderr)
        return 2
    return _run(
        ["taskiq", "worker", f"{project}.tkq:broker"],
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
    p_dev.add_argument(
        "--otlp",
        action="store_true",
        help="Include the local OpenTelemetry/Grafana Compose overlay",
    )
    compose_choice = p_dev.add_mutually_exclusive_group()
    compose_choice.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse an existing Compose project without rebuilding",
    )
    compose_choice.add_argument(
        "--new",
        dest="new_stack",
        action="store_true",
        help="Create a new isolated Compose project",
    )
    p_dev.set_defaults(func=cmd_dev)

    p_build = sub.add_parser("build", help="Build production Docker image")
    p_build.set_defaults(func=cmd_build)

    p_start = sub.add_parser("start", help="Start the production application")
    p_start.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p_start.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p_start.set_defaults(func=cmd_start)

    p_migrate = sub.add_parser("migrate", help="Apply database migrations")
    p_migrate.set_defaults(func=cmd_migrate)

    p_seed = sub.add_parser("seed", help="Run project seed data")
    p_seed.add_argument("name", nargs="?")
    p_seed.set_defaults(func=cmd_seed)

    p_gen = sub.add_parser("generate", help="Scaffold a business module")
    p_gen.add_argument("module", help="dotted path, e.g. crm.leads")
    p_gen.add_argument(
        "--fields",
        nargs="*",
        default=[],
        help="field specs name:type",
    )
    p_gen.set_defaults(func=cmd_generate)

    p_eval = sub.add_parser("eval", help="Run the project evaluation dataset")
    p_eval.add_argument("dataset", nargs="?", default="tests/evals/golden.yaml")
    p_eval.set_defaults(func=cmd_eval)

    p_jobs = sub.add_parser("jobs", help="Manage background jobs")
    jobs_sub = p_jobs.add_subparsers(dest="jobs_command", required=True)
    p_replay = jobs_sub.add_parser("replay", help="Replay dead-letter jobs")
    p_replay.add_argument("ids", nargs="*", help="DLQ item IDs; omit to replay the available queue")
    p_replay.set_defaults(func=cmd_jobs_replay)

    p_deploy = sub.add_parser("deploy", help="Deploy with the generated Helm chart")
    p_deploy.add_argument("environment", choices=("staging", "prod", "prod-s2", "prod-s3", "prod-s4"))
    p_deploy.add_argument("--release", default="nk-backend")
    p_deploy.add_argument("--namespace", default="nk")
    p_deploy.add_argument(
        "--image-digest",
        required=True,
        help="Immutable application image digest (sha256:...).",
    )
    p_deploy.add_argument("--dry-run", action="store_true")
    p_deploy.set_defaults(func=cmd_deploy)

    p_scale = sub.add_parser("scale-status", help="Show the configured scale stage")
    p_scale.set_defaults(func=cmd_scale_status)

    p_worker = sub.add_parser("worker", help="Start the background worker")
    p_worker.set_defaults(func=cmd_worker)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    code = int(args.func(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
