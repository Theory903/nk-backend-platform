from importlib.metadata import entry_points
from unittest.mock import Mock

import pytest

import fastapi_template.__main__ as generator_cli


def test_init_accepts_next_style_project_name(monkeypatch):
    run_command = Mock()
    monkeypatch.setattr(generator_cli, "run_command", run_command)
    monkeypatch.setattr(generator_cli.sys, "argv", ["nk"])

    generator_cli.main(["init", "my_app", "--profile", "minimal"])

    run_command.assert_called_once_with(
        generator_cli.generate_project,
        argv=["--name", "my_app", "--profile", "minimal"],
        prog_name="nk init",
    )


def test_init_accepts_product_use_case(monkeypatch):
    run_command = Mock()
    monkeypatch.setattr(generator_cli, "run_command", run_command)
    monkeypatch.setattr(generator_cli.sys, "argv", ["nk"])

    generator_cli.main(["init", "reliant", "--use-case", "enterprise-saas"])

    run_command.assert_called_once_with(
        generator_cli.generate_project,
        argv=["--name", "reliant", "--use-case", "enterprise-saas"],
        prog_name="nk init",
    )


def test_use_case_resolves_profile_before_generation(monkeypatch):
    callback = Mock()
    monkeypatch.setattr(generator_cli, "generate_project", callback)
    monkeypatch.setattr(generator_cli.sys, "argv", ["nk"])

    with pytest.raises(SystemExit) as result:
        generator_cli.main(
            ["init", "reliant", "--use-case", "enterprise-saas", "--quiet"],
        )
    assert result.value.code == 0

    context = callback.call_args.args[0]
    assert context.use_case == "enterprise-saas"
    assert context.profile == "saas"
    assert context.db == "postgresql"


def test_explicit_profile_wins_over_use_case(monkeypatch):
    callback = Mock()
    monkeypatch.setattr(generator_cli, "generate_project", callback)
    monkeypatch.setattr(generator_cli.sys, "argv", ["nk"])

    with pytest.raises(SystemExit) as result:
        generator_cli.main(
            [
                "init",
                "custom_profile",
                "--use-case",
                "ai-knowledge",
                "--profile",
                "minimal",
                "--quiet",
            ],
        )
    assert result.value.code == 0

    context = callback.call_args.args[0]
    assert context.use_case == "ai-knowledge"
    assert context.profile == "minimal"
    assert context.enable_llm is False


def test_create_remains_a_legacy_alias(monkeypatch):
    run_command = Mock()
    monkeypatch.setattr(generator_cli, "run_command", run_command)

    generator_cli.main(["create", "--name", "my_app"])

    run_command.assert_called_once_with(
        generator_cli.generate_project,
        argv=["--name", "my_app"],
        prog_name=None,
    )


def test_nk_console_script_is_published():
    scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}

    assert scripts["nk"] == "fastapi_template.__main__:main"
