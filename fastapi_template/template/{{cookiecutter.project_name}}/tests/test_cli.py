import socket
from argparse import Namespace

import pytest

from {{cookiecutter.project_name}} import cli
from {{cookiecutter.project_name}}.cli import _choose_compose_project


def test_existing_compose_project_can_be_reused(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "{{cookiecutter.project_name}}.cli._compose_project_is_used",
        lambda root, project_name: True,
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "")

    project_name, reuse = _choose_compose_project(
        tmp_path,
        {"project": "demo"},
        Namespace(reuse=False, new_stack=False),
    )

    assert project_name == "demo"
    assert reuse is True


def test_new_compose_project_gets_an_isolated_name(monkeypatch, tmp_path):
    existing = {"demo", "demo-2"}
    monkeypatch.setattr(
        "{{cookiecutter.project_name}}.cli._compose_project_is_used",
        lambda root, project_name: project_name in existing,
    )

    project_name, reuse = _choose_compose_project(
        tmp_path,
        {"project": "demo"},
        Namespace(reuse=False, new_stack=True),
    )

    assert project_name == "demo-3"
    assert reuse is False


def test_reuse_requires_an_existing_compose_project(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "{{cookiecutter.project_name}}.cli._compose_project_is_used",
        lambda root, project_name: False,
    )

    with pytest.raises(ValueError, match="does not exist"):
        _choose_compose_project(
            tmp_path,
            {"project": "demo"},
            Namespace(reuse=True, new_stack=False),
        )


def test_explicit_occupied_port_has_actionable_error(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        occupied_port = listener.getsockname()[1]
        monkeypatch.setenv("NK_REDIS_PORT", str(occupied_port))

        with pytest.raises(ValueError, match="already in use"):
            cli._select_port("NK_REDIS_PORT", 6379)


def test_auto_port_selection_skips_occupied_port(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        occupied_port = listener.getsockname()[1]
        monkeypatch.delenv("NK_REDIS_PORT", raising=False)

        selected_port = cli._select_port("NK_REDIS_PORT", occupied_port)

    assert selected_port != occupied_port
    assert selected_port > occupied_port


def test_reuse_does_not_rebuild_or_change_the_existing_stack(monkeypatch, tmp_path):
    commands = []
    container_ports = []

    def get_api_port(root, project, container_port):
        container_ports.append(container_port)
        return 8012

    monkeypatch.setattr(cli, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "needs_compose", lambda root: True)
    monkeypatch.setattr(cli, "_load_manifest", lambda root: {"project": "demo"})
    monkeypatch.setattr(
        cli,
        "_choose_compose_project",
        lambda root, manifest, args: ("demo", True),
    )
    monkeypatch.setattr(
        cli,
        "_compose_api_port",
        get_api_port,
    )
    monkeypatch.setattr(
        cli,
        "_run",
        lambda command, cwd=None: commands.append(command) or 0,
    )
    monkeypatch.setattr(cli.shutil, "which", lambda program: "/usr/bin/docker")

    result = cli.cmd_dev(Namespace(app_only=False, reuse=True, new_stack=False))

    assert result == 0
    assert container_ports == [8000]
    assert commands == [
        [
            "docker",
            "compose",
            "--project-name",
            "demo",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.dev.yml",
            "up",
            "--no-build",
            "--no-recreate",
        ]
    ]


def test_build_tags_all_application_images(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(cli, "_project_root", lambda: tmp_path)
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    monkeypatch.setattr(
        cli,
        "_load_manifest",
        lambda root: {
            "project": "demo",
            "providers": {"orm": "sqlalchemy"},
            "modules": {"taskiq": True, "migrations": True},
        },
    )
    monkeypatch.setattr(cli.shutil, "which", lambda program: "/usr/bin/docker")
    monkeypatch.setattr(
        cli,
        "_run",
        lambda command, cwd=None: commands.append(command) or 0,
    )

    result = cli.cmd_build(Namespace())

    assert result == 0
    assert commands == [
        [
            "docker",
            "build",
            "--target",
            "prod",
            "--tag",
            "demo-api:local",
            "--tag",
            "demo-api:latest",
            "--tag",
            "demo-worker:local",
            "--tag",
            "demo-worker:latest",
            "--tag",
            "demo-migrator:local",
            "--tag",
            "demo-migrator:latest",
            ".",
        ]
    ]
