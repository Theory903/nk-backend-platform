#!/usr/bin/env python
import os
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


def run_cmd(cmd: str, ignore_error: bool = False):
    out = subprocess.run(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_env(),
    )
    if out.returncode != 0 and not ignore_error:
        # offline / cache miss: single yellow line, no red dump
        stderr = (out.stderr or b"").decode(errors="replace")
        if "uv sync" in cmd and ("offline" in stderr.lower() or "Failed to download" in stderr or "Network connectivity" in stderr or "Unable to find lockfile" in stderr):
            cprint("[WARN] `uv sync` skipped (offline or cache miss). Run `uv sync` again with network.", "yellow")
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


def init_repo():
    run_cmd("git init")
    cprint(" Git repository initialized", "green")
    run_cmd("git add .")
    cprint("🐍 Installing python dependencies with uv", "green")
    # --frozen, offline-aware, VIRTUAL_ENV sanitized
    try:
        run_cmd("uv sync --frozen")
    except ValueError:
        cprint("[WARN] `uv sync` skipped (offline or cache miss). Run `uv sync` again with network.", "yellow")
    run_cmd("uv run pre-commit install", ignore_error=True)
    cprint("📚🖌️📄📏 Tidying up the project", "green")
    for _ in range(2):
        run_cmd("uv run pre-commit run -a", ignore_error=True)
    run_cmd("git add .", ignore_error=True)
    cprint("🚀Creating your first commit", "green")
    run_cmd("git commit -m 'Initial commit'", ignore_error=True)


if __name__ == "__main__":
    delete_resources_for_disabled_features()
    replace_resources()
    clean_frontend_artifacts()
    try:
        init_repo()
    except ValueError:
        pass
