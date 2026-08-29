from pathlib import Path
import sys

from cookiecutter.exceptions import FailedHookException, OutputDirExistsException
from cookiecutter.main import cookiecutter
from termcolor import cprint

from fastapi_template.cli import run_command
from fastapi_template.input_model import BuilderContext
from fastapi_template.validation import validate_context

script_dir = Path(__file__).parent


def _print_next_steps(project_name: str) -> None:
    """Create-next-app style post-generate hints (4 lines)."""
    cprint(f"\n  cd {project_name}", "cyan")
    cprint("  uv sync", "cyan")
    cprint("  uv run nk doctor", "cyan")
    cprint("  uv run nk dev\n", "cyan")


def generate_project(context: BuilderContext) -> None:
    """
    Generate actual project with given context.

    :param context: builder_context
    """
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
    _print_next_steps(str(name))


def main() -> None:
    """Starting point. Accepts optional ``create`` verb alias."""
    if len(sys.argv) > 1 and sys.argv[1] == "create":
        sys.argv.pop(1)
    run_command(generate_project)


if __name__ == "__main__":
    main()
