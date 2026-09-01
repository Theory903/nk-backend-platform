from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence

from cookiecutter.exceptions import FailedHookException, OutputDirExistsException
from cookiecutter.main import cookiecutter
from termcolor import cprint

from fastapi_template.cli import run_command
from fastapi_template.config import resolve_config
from fastapi_template.input_model import BuilderContext
from fastapi_template.profiles import PROFILE_OPTION_DEFAULTS
from fastapi_template.validation import validate_context

script_dir = Path(__file__).parent


def _print_next_steps(project_name: str) -> None:
    """Create-next-app style post-generate hints."""
    cprint(f"\n  cd {project_name}", "cyan")
    cprint("  uv run nk doctor", "cyan")
    cprint("  uv run nk dev\n", "cyan")


def _print_architecture(context: BuilderContext) -> None:
    """Print the resolved architecture as a post-generation contract."""
    config = resolve_config(context)
    database = config.database
    orm = config.orm
    data_layer = "none" if database == "none" else f"{database} + {orm}"
    brokers = [
        name
        for name, key in (
            ("RabbitMQ", "enable_rmq"),
            ("Kafka", "enable_kafka"),
            ("NATS", "enable_nats"),
        )
        if config.modules.get(key.removeprefix("enable_"), False)
    ]
    queue = "Taskiq" if config.modules.get("taskiq", False) else "none"
    if brokers:
        queue = f"{queue} + {', '.join(brokers)}"
    elif config.modules.get("redis", False):
        queue = f"{queue} + Redis" if queue != "none" else "Redis"

    observability = [
        name
        for name, key in (
            ("Prometheus", "prometheus_enabled"),
            ("OpenTelemetry", "opentelemetry"),
            ("Sentry", "sentry_enabled"),
        )
        if config.observability.get(
            key.removesuffix("_enabled"),
            config.observability.get(key, False),
        )
    ]
    runtime = "Gunicorn" if config.modules.get("gunicorn", False) else "Uvicorn"

    cprint("\nResolved architecture", "green")
    if config.use_case:
        cprint(f"  Use case: {config.use_case}", "cyan")
    if config.profile:
        cprint(f"  Profile: {config.profile}", "cyan")
    cprint(f"  API: {config.api_type.upper()}", "cyan")
    cprint(f"  Data: {data_layer}", "cyan")
    cprint(f"  Runtime: {runtime}", "cyan")
    cprint(f"  Async work: {queue}", "cyan")
    cprint(
        f"  Observability: {', '.join(observability) or 'application logs only'}",
        "cyan",
    )


def generate_project(context: BuilderContext) -> None:
    """
    Generate actual project with given context.

    :param context: builder_context
    """
    # ``cookiecutter.json`` stores option metadata for the interactive
    # generator. Always override optional selectors so omitted values are
    # rendered as empty metadata rather than the metadata dictionaries.
    context.data.setdefault("profile", None)
    context.data.setdefault("use_case", None)
    for key, value in PROFILE_OPTION_DEFAULTS.items():
        context.data.setdefault(key, value)
    context.data.setdefault("orm", "none")

    try:
        validate_context(context)
    except ValueError as exc:
        cprint(str(exc), "red")
        raise SystemExit(1) from exc
    try:
        cookiecutter(
            template=f"{script_dir}/template",
            extra_context=context.dict(),
            default_config=True,
            no_input=True,
            overwrite_if_exists=context.force,
        )
    except (FailedHookException, OutputDirExistsException) as exc:
        if isinstance(exc, OutputDirExistsException):
            cprint("Directory with such name already exists!", "red")
        return

    name = context.project_name or "project"
    cprint("Project successfully generated.", "green")
    _print_architecture(context)
    _print_next_steps(str(name))


def _normalize_init_args(argv: Sequence[str]) -> list[str]:
    """Translate ``nk init NAME`` into the existing generator options."""
    args = list(argv)
    if args and args[0] in {"init", "create"}:
        args.pop(0)
        if args and not args[0].startswith("-"):
            args[0:1] = ["--name", args[0]]
    return args


def _program_name() -> str:
    """Return the executable name used in Click's help output."""
    executable = Path(sys.argv[0]).name
    if executable in {"__main__", "__main__.py"}:
        return "fastapi_template"
    return executable


def main(argv: Sequence[str] | None = None) -> None:
    """Run the generator as ``nk init NAME`` or its legacy aliases."""
    raw_args = list(sys.argv[1:] if argv is None else argv)
    command = raw_args[0] if raw_args and raw_args[0] in {"init", "create"} else None
    run_command(
        generate_project,
        argv=_normalize_init_args(raw_args),
        prog_name=f"{_program_name()} init" if command == "init" else None,
    )


if __name__ == "__main__":
    main()
