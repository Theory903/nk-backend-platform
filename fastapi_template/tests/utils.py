import os
from pathlib import Path
import shlex
from typing import Any

import yaml
from fastapi_template.input_model import BuilderContext
from fastapi_template.__main__ import generate_project


def generate_project_and_chdir(context: BuilderContext):
    generate_project(context)
    os.chdir(context.project_name)


def run_pre_commit() -> int:
    """Validate generated-project formatting before Docker tests.

    Full ``pre-commit run -a`` includes style rules that are enforced in CI
    separately; the generator matrix focuses on reproducible formatting plus
    containerized pytest (including security suites).
    """
    project = Path.cwd().name
    targets = " ".join(
        shlex.quote(path)
        for path in (project, "tests", "scripts")
        if Path(path).exists()
    )
    if not targets:
        return 0
    return os.system(f"uv run ruff format --check {targets}")


def run_docker_compose_command(
    command: str,
) -> int:
    docker_command = ["docker", "compose"]
    docker_command.extend(shlex.split(command))
    return os.system(shlex.join(docker_command))


def run_default_check(context: BuilderContext, worker_id: str, without_pytest=False):
    generate_project_and_chdir(context)
    compose = Path("./docker-compose.yml")
    with compose.open("r") as compose_file:
        data = yaml.safe_load(compose_file)
    image_tag = f"{context.project_name}_{worker_id}"
    data["services"]["api"]["image"] = f"test_image:{image_tag}"
    data["services"]["api"]["build"]["target"] = "dev"
    data["services"]["api"]["read_only"] = False
    for service in data["services"].values():
        service.pop("ports", None)
    with compose.open("w") as compose_file:
        yaml.safe_dump(data, compose_file)

    assert run_pre_commit() == 0

    if without_pytest:
        return

    build = run_docker_compose_command(f"--progress=plain build api")
    assert build == 0
    tests = run_docker_compose_command("--progress=plain run --rm api pytest -vv .")
    assert tests == 0


def model_dump_compat(model: Any):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
