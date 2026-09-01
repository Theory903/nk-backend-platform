#!/usr/bin/env python
import os
import re
import shutil
import subprocess
import tomllib
import shlex

from termcolor import cprint, colored
from pathlib import Path

CONDITIONAL_MANIFEST = Path("conditional_files.toml")
REPLACE_MANIFEST = Path("replaceable_files.toml")


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    return env


def delete_resource(resource: Path):
    if resource.is_file():
        resource.unlink()
    elif resource.is_dir():
        shutil.rmtree(resource)


def remove_empty_dirs(root: Path = Path(".")) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def delete_resources_for_disabled_features():
    with CONDITIONAL_MANIFEST.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)

        for feature in manifest["features"]:
            enabled = feature["enabled"].lower() != "true"
            name = feature["name"]
            resources = feature["resources"]
            if enabled:
                text = "{} resources for disabled feature {}...".format(
                    colored("Removing", color="red"),
                    colored(name, color="magenta", attrs=["underline"]),
                )
                print(text)
                for resource in resources:
                    delete_resource(Path(resource))
    remove_empty_dirs()
    delete_resource(CONDITIONAL_MANIFEST)
    cprint("cleanup complete!", color="green")


def replace_resources():
    print(
        "⭐ Placing {} nicely in your {} ⭐".format(
            colored("resources", color="green"), colored("new project", color="blue")
        )
    )
    with REPLACE_MANIFEST.open("rb") as replace_manifest:
        manifest = tomllib.load(replace_manifest)
        for substitution in manifest["sub"]:
            target = Path(substitution["target"])
            replaces = [Path(path) for path in substitution["replaces"]]
            delete_resource(target)
            for src_file in replaces:
                if src_file.exists():
                    shutil.move(src_file, target)
    delete_resource(REPLACE_MANIFEST)
    print(
        "Resources are happy to be where {}.".format(
            colored("they are needed the most", color="green", attrs=["underline"])
        )
    )


def replace_helm_environment_prefix() -> None:
    """Resolve the package-specific settings prefix in copied Helm files."""
    prefix = Path.cwd().name.upper()
    helm_root = Path("deploy/helm")
    if not helm_root.exists():
        return
    platform = Path("platform.yaml").read_text(encoding="utf-8")
    modules = {
        name: bool(
            re.search(
                rf"^\s+{name}:\s+true\s*$",
                platform,
                flags=re.MULTILINE | re.IGNORECASE,
            ),
        )
        for name in ("taskiq", "migrations", "users", "redis")
    }
    orm_match = re.search(
        r"^\s+orm:\s+([^\s]+)\s*$",
        platform,
        flags=re.MULTILINE,
    )
    database_match = re.search(
        r"^\s+database:\s+([^\s]+)\s*$",
        platform,
        flags=re.MULTILINE,
    )
    database_enabled = database_match is not None and (
        database_match.group(1).lower() != "none"
    )
    enable_migrate = modules["migrations"] and (
        orm_match is None or orm_match.group(1) != "psycopg"
    )
    replacements = {
        "__APP_ENV_PREFIX__": prefix,
        "__OWNER_ROLE__": f"{Path.cwd().name}_owner",
        "__ENABLE_TASKIQ__": str(modules["taskiq"]).lower(),
        "__ENABLE_MIGRATE__": str(enable_migrate).lower(),
        "__SECURITY_REQUIRE_AUTH__": str(modules["users"]).lower(),
        "__IDENTITY_ENABLED__": str(modules["users"]).lower(),
        "__DATABASE_ENABLED__": str(database_enabled).lower(),
        "__AUTH_STORE_BACKEND__": (
            "redis"
            if modules["redis"]
            else "sql"
        ),
    }
    for path in helm_root.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if any(marker in content for marker in replacements):
            for marker, replacement in replacements.items():
                content = content.replace(marker, replacement)
            path.write_text(
                content,
                encoding="utf-8",
            )


def run_cmd(cmd: str, ignore_error: bool = False, timeout: int = 120):
    try:
        out = subprocess.run(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_clean_env(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        if ignore_error:
            cprint(f"[WARN] Command `{cmd}` timed out after {timeout}s.", "yellow")
            return subprocess.CompletedProcess(
                args=shlex.split(cmd),
                returncode=1,
                stdout=exc.stdout or b"",
                stderr=exc.stderr or b"",
            )
        cprint(f"[WARN] Command `{cmd}` timed out after {timeout}s.", "yellow")
        raise ValueError(f"command timed out: {cmd}") from exc
    if out.returncode != 0 and not ignore_error:
        # offline / cache miss: single yellow line, no red dump
        stderr = (out.stderr or b"").decode(errors="replace")
        offline_errors = (
            "offline" in stderr.lower()
            or "Failed to download" in stderr
            or "Network connectivity" in stderr
            or "Unable to find lockfile" in stderr
        )
        if "uv sync" in cmd and offline_errors:
            cprint(
                "[WARN] `uv sync` skipped (offline or cache miss). "
                "Run `uv sync` again with network.",
                "yellow",
            )
            return out
        cprint(" WARNING ".center(50, "="), "yellow")
        cprint(
            f"[WARN] Command `{cmd}` was not successfull. Check output below.",
            "yellow",
        )
        cprint(
            "However, the project was generated. So it could be a false-positive.",
            "yellow",
        )
        if out.stdout:
            cprint(out.stdout.decode(errors="replace"), "red")
        if out.stderr:
            cprint(out.stderr.decode(errors="replace"), "red")
        raise ValueError()
    return out


def clean_frontend_artifacts():
    """Drop any build artefacts that leaked in from the template checkout.

    Cookiecutter copies the template working tree rather than its git index, so
    a maintainer who ran `npm install` or `npm run build` locally would
    otherwise ship `node_modules/` and a stale bundle into every new project.
    """
    for artifact in (
        Path("frontend/node_modules"),
        Path("frontend/dist"),
        Path("frontend/tsconfig.tsbuildinfo"),
        Path("{{cookiecutter.project_name}}/static/studio/dist"),
    ):
        if artifact.exists():
            cprint(f"Removing copied build artifact {artifact}...", "red")
            delete_resource(artifact)

    for path in sorted(
        Path(".").rglob("*"),
        key=lambda candidate: len(candidate.parts),
        reverse=True,
    ):
        if path.is_dir() and path.name == "__pycache__":
            delete_resource(path)
        elif path.is_file() and path.suffix == ".pyc":
            delete_resource(path)
    remove_empty_dirs()


def validate_compose_configuration():
    """Validate generated Compose files when Docker is installed."""
    if shutil.which("docker") is None:
        return
    docker_info = run_cmd("docker info", ignore_error=True, timeout=2)
    if docker_info.returncode != 0:
        cprint(
            "[WARN] Docker daemon unavailable; skipping Compose validation.",
            "yellow",
        )
        return

    compose_files = [
        "docker-compose.yml",
        "docker-compose.prod.yml",
    ]
    if Path("deploy/docker-compose.otlp.yml").exists():
        compose_files.append("deploy/docker-compose.otlp.yml")

    command = (
        "env "
        "ALLOWED_HOSTS=localhost "
        "CORS_ALLOWED_ORIGINS=[] "
        "DB_USER=validation-user "
        "DB_PASSWORD=validation-password "
        "DB_ADMIN_USER=validation-admin "
        "DB_ADMIN_PASSWORD=validation-admin-password "
        "DB_OWNER_ROLE=validation-owner "
        "DB_NAME=validation-db "
        "DB_ROOT_PASSWORD=validation-root-password "
        "USERS_SECRET=validation-users-secret-32chars!! "
        "AUTH_STORE_BACKEND=validation-backend "
        "REDIS_PASSWORD=validation-redis-password "
        "METRICS_AUTH_TOKEN=validation-metrics-token "
        "RABBITMQ_USER=validation-rabbit-user "
        "RABBITMQ_PASSWORD=validation-rabbit-password "
        "GRAFANA_ADMIN_PASSWORD=validation-only "
        "METRICS_AUTH_TOKEN=validation-metrics-token "
        "docker compose"
    )
    command += " " + " ".join(f"-f {shlex.quote(path)}" for path in compose_files)
    command += " config --quiet"
    run_cmd(command, timeout=30)


def format_generated_project() -> None:
    """Format generated sources so first pre-commit run is a no-op."""
    if shutil.which("uv") is None:
        cprint(
            "[WARN] uv unavailable; skipping generated-project formatting.",
            "yellow",
        )
        return
    project = Path.cwd().name
    targets = " ".join(
        shlex.quote(path)
        for path in (project, "tests", "scripts")
        if Path(path).exists()
    )
    if not targets:
        return
    cprint("📏 Formatting generated project sources", "green")
    run_cmd(f"uv run ruff format {targets}", ignore_error=True, timeout=120)


def ensure_lockfile() -> None:
    """Create uv.lock during generation for reproducible CI and builds."""
    if Path("uv.lock").exists():
        return
    if shutil.which("uv") is None:
        raise RuntimeError(
            "uv is required to generate the locked dependency graph",
        )
    cprint("🔒 Creating uv.lock for reproducible environments", "green")
    result = run_cmd("uv lock --offline", ignore_error=True, timeout=60)
    if result.returncode != 0:
        cprint(
            "[WARN] Offline lock failed; retrying uv lock with network access.",
            "yellow",
        )
        result = run_cmd("uv lock", ignore_error=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(
            "could not create uv.lock; ensure uv can resolve dependencies",
        )


def init_repo():
    run_cmd("git init")
    cprint(" Git repository initialized", "green")
    run_cmd("git add .")
    install_requested = os.getenv("NK_GENERATOR_INSTALL", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if install_requested:
        cprint("🐍 Installing python dependencies with uv", "green")
        try:
            run_cmd("uv sync --locked", timeout=120)
        except ValueError:
            cprint(
                "[WARN] `uv sync` skipped (offline, cache miss, or timeout). "
                "Run `uv sync` again with network.",
                "yellow",
            )
    else:
        cprint(
            "🐍 Dependencies not installed during generation; run `uv sync` "
            "or set NK_GENERATOR_INSTALL=1.",
            "yellow",
        )
    run_hooks = os.getenv("NK_GENERATOR_RUN_HOOKS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if run_hooks:
        run_cmd("uv run pre-commit install", ignore_error=True, timeout=60)
        cprint("📚🖌️📄📏 Tidying up the project", "green")
        run_cmd("uv run pre-commit run -a", ignore_error=True, timeout=120)
    else:
        cprint(
            "⏭️ Skipping pre-commit hooks; set NK_GENERATOR_RUN_HOOKS=1 to run them.",
            "yellow",
        )
    run_cmd("git add .", ignore_error=True)
    cprint("🚀Creating your first commit", "green")
    run_cmd("git commit -m 'Initial commit'", ignore_error=True)


if __name__ == "__main__":
    delete_resources_for_disabled_features()
    replace_resources()
    replace_helm_environment_prefix()
    clean_frontend_artifacts()
    ensure_lockfile()
    format_generated_project()
    validate_compose_configuration()
    try:
        init_repo()
    except ValueError:
        pass
