from pathlib import Path

import pytest

from {{cookiecutter.project_name}}.core.feature_flags import (
    FeatureFlagError,
    FeatureFlags,
    all_flags,
    get_feature_flags,
    is_enabled,
)


def test_flags_default() -> None:
    assert is_enabled("nonexistent_flag_xyz", default=False) is False
    assert is_enabled("nonexistent_flag_xyz", default=True) is True


def test_all_flags_returns_dict() -> None:
    flags = all_flags()
    assert isinstance(flags, dict)


def test_get_feature_flags_returns_service() -> None:
    assert isinstance(get_feature_flags(), FeatureFlags)


def test_runtime_override_set_and_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "platform.yaml"
    config.write_text("project: test\nfeature_flags:\n  agent.graph: false\n", encoding="utf-8")
    flags = FeatureFlags(config_path=config)

    assert flags.is_enabled("agent.graph") is False

    flags.set("agent.graph", True)
    resolved = flags.resolve("agent.graph")
    assert resolved.enabled is True
    assert resolved.source == "runtime"

    flags.unset("agent.graph")
    assert flags.is_enabled("agent.graph") is False


def test_clear_overrides(tmp_path: Path) -> None:
    config = tmp_path / "platform.yaml"
    config.write_text("project: test\nfeature_flags:\n  demo.flag: false\n", encoding="utf-8")
    flags = FeatureFlags(config_path=config)

    flags.set("demo.flag", True)
    flags.clear_overrides()
    assert flags.is_enabled("demo.flag") is False


def test_resolve_metadata_from_config(tmp_path: Path) -> None:
    config = tmp_path / "platform.yaml"
    config.write_text(
        "project: test\n"
        "feature_flags:\n"
        "  rich.flag:\n"
        "    enabled: true\n"
        "    source: platform\n"
        "    metadata:\n"
        "      owner: platform\n",
        encoding="utf-8",
    )
    flags = FeatureFlags(config_path=config)
    resolved = flags.resolve("rich.flag")
    assert resolved.enabled is True
    assert resolved.source == "platform"
    assert resolved.metadata == {"owner": "platform"}


def test_reload_picks_up_config_changes(tmp_path: Path) -> None:
    config = tmp_path / "platform.yaml"
    config.write_text("project: test\nfeature_flags:\n  reload.me: false\n", encoding="utf-8")
    flags = FeatureFlags(config_path=config)
    assert flags.is_enabled("reload.me") is False

    config.write_text("project: test\nfeature_flags:\n  reload.me: true\n", encoding="utf-8")
    flags.reload()
    assert flags.is_enabled("reload.me") is True


def test_environment_override_via_module_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEATURE_AGENT_GRAPH", "true")
    assert is_enabled("agent.graph", default=False) is True

    monkeypatch.setenv("FEATURE_AGENT_GRAPH", "0")
    assert is_enabled("agent.graph", default=True) is False


def test_all_flags_applies_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc = get_feature_flags()
    svc.set("agent.graph", False)
    try:
        monkeypatch.setenv("FEATURE_AGENT_GRAPH", "true")
        result = all_flags()
        assert result["agent.graph"] is True
    finally:
        svc.unset("agent.graph")
        monkeypatch.delenv("FEATURE_AGENT_GRAPH", raising=False)


def test_empty_flag_name_raises(tmp_path: Path) -> None:
    flags = FeatureFlags(config_path=tmp_path / "missing.yaml")
    with pytest.raises(FeatureFlagError, match="must not be empty"):
        flags.is_enabled("   ")


def test_names_sorted(tmp_path: Path) -> None:
    config = tmp_path / "platform.yaml"
    config.write_text(
        "project: test\nfeature_flags:\n  zeta: true\n  alpha: false\n",
        encoding="utf-8",
    )
    flags = FeatureFlags(config_path=config)
    assert flags.names() == ["alpha", "zeta"]
