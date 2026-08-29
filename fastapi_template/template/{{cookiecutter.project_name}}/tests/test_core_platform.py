"""Tests for typed platform.yaml loading, validation, and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from {{cookiecutter.project_name}}.core.platform import (
    PlatformConfig,
    ProvidersConfig,
    get_platform_config,
    reload_platform_config,
    validate_platform_config,
)


@pytest.fixture(autouse=True)
def _clear_platform_cache() -> None:
    get_platform_config.cache_clear()
    yield
    get_platform_config.cache_clear()


def _write_manifest(path: Path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_platform_manifest_loads() -> None:
    """
    The generated platform.yaml parses into a typed config.
    """
    config = get_platform_config()

    assert config.project
    assert config.providers.database == "{{ cookiecutter.db_info.name }}"
    assert config.module_enabled("agents") is {{ cookiecutter.enable_agents }}


def test_module_lookup_defaults_to_disabled() -> None:
    """
    Unknown modules report disabled instead of raising.
    """
    config = get_platform_config()

    assert config.module_enabled("never-defined-module") is False


def test_missing_manifest_raises(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-platform.yaml"
    with pytest.raises(FileNotFoundError, match="platform manifest not found"):
        get_platform_config(str(missing))


def test_empty_yaml_raises(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path / "empty.yaml", "")
    with pytest.raises(ValueError, match="platform manifest is empty"):
        get_platform_config(path)


def test_invalid_root_raises(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path / "list.yaml", "- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="root must be a mapping"):
        get_platform_config(path)


def test_invalid_yaml_syntax_raises(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path / "bad.yaml", "project: [\nunclosed\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        get_platform_config(path)


def test_validation_error_missing_project(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path / "noproj.yaml",
        "profile: bare\nmodules: {}\n",
    )
    with pytest.raises(ValueError, match="invalid platform configuration"):
        get_platform_config(path)


def test_defaults_for_optional_sections(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path / "minimal.yaml",
        "project: demo\n",
    )
    config = get_platform_config(path)

    assert config.project == "demo"
    assert config.profile == ""
    assert isinstance(config.providers, ProvidersConfig)
    assert config.providers.database == "none"
    assert config.modules == {}
    assert config.observability.prometheus is False


def test_module_enabled_and_provider_helpers(tmp_path: Path) -> None:
    path = _write_manifest(
        tmp_path / "helpers.yaml",
        "project: demo\n"
        "providers:\n"
        "  database: postgresql\n"
        "  orm: sqlalchemy\n"
        "modules:\n"
        "  agents: true\n"
        "  audit: false\n"
        "observability:\n"
        "  sentry: true\n",
    )
    config = get_platform_config(path)

    assert config.module_enabled("agents") is True
    assert config.module_enabled("audit") is False
    assert config.module_enabled("missing") is False
    assert config.provider("database") == "postgresql"
    assert config.provider("orm") == "sqlalchemy"
    assert config.provider("unknown", default="fallback") == "fallback"
    assert config.observability_enabled("sentry") is True
    assert config.observability_enabled("prometheus") is False
    assert config.observability_enabled("nope") is False


def test_reload_clears_cache_and_reloads_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text("project: first\nmodules:\n  agents: false\n", encoding="utf-8")
    second.write_text("project: second\nmodules:\n  agents: true\n", encoding="utf-8")

    monkeypatch.setattr(
        "{{cookiecutter.project_name}}.core.platform.manifest_path",
        lambda: first,
    )
    cfg = get_platform_config()
    assert cfg.project == "first"
    assert cfg.module_enabled("agents") is False

    # Mutate the default file; cached value must stick until reload.
    first.write_text("project: first-updated\nmodules:\n  agents: true\n", encoding="utf-8")
    assert get_platform_config().project == "first"

    reloaded = reload_platform_config()
    assert reloaded.project == "first-updated"
    assert reloaded.module_enabled("agents") is True

    # reload always targets the default path, not a previously loaded custom path.
    custom = get_platform_config(str(second))
    assert custom.project == "second"
    again = reload_platform_config()
    assert again.project == "first-updated"


def test_validate_platform_config_bypasses_stale_cache(tmp_path: Path) -> None:
    path = tmp_path / "v.yaml"
    path.write_text("project: before\n", encoding="utf-8")
    assert get_platform_config(str(path)).project == "before"

    path.write_text("project: after\n", encoding="utf-8")
    # Stale cache would still say "before" without validate/clear.
    assert get_platform_config(str(path)).project == "before"

    fresh = validate_platform_config(str(path))
    assert fresh.project == "after"
    assert isinstance(fresh, PlatformConfig)


def test_directory_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is not a file"):
        get_platform_config(str(tmp_path))
