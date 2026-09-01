"""Tests for P21 plugin kernel."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
PKG = TEMPLATE_ROOT / "{{cookiecutter.project_name}}"
KERNEL = PKG / "kernel" / "plugins"


def test_p21_kernel_modules_exist() -> None:
    for name in (
        "contracts.py",
        "registry.py",
        "lifecycle.py",
        "capabilities.py",
        "events.py",
        "bootstrap.py",
        "catalog.yaml",
        "__init__.py",
    ):
        assert (KERNEL / name).is_file(), name
    assert (PKG / "kernel" / "__init__.py").is_file()


def test_plugin_contract_fields() -> None:
    text = (KERNEL / "contracts.py").read_text(encoding="utf-8")
    for token in ("PluginManifest", "PluginType", "provides", "requires", "permissions"):
        assert token in text


def test_catalog_declares_core_primitives() -> None:
    text = (KERNEL / "catalog.yaml").read_text(encoding="utf-8")
    for plugin in (
        "model_gateway",
        "tool_gateway",
        "agent_runtime",
        "session_runtime",
        "harness",
        "security",
        "observability",
    ):
        assert plugin in text


def test_bootstrap_wires_plugin_kernel() -> None:
    text = (PKG / "agents" / "bootstrap.py").read_text(encoding="utf-8")
    assert "build_plugin_kernel" in text
    assert "plugin_kernel" in text


def test_capabilities_topological_sort() -> None:
    text = (KERNEL / "capabilities.py").read_text(encoding="utf-8")
    assert "resolve_load_order" in text
    assert "capability_index" in text


def test_cli_plugins_commands() -> None:
    text = (PKG / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert "cmd_ai_plugins_list" in text
    assert "cmd_ai_plugins_health" in text
    assert '"plugins"' in text


def test_platform_manifest_plugins_section() -> None:
    text = (TEMPLATE_ROOT / "platform.yaml").read_text(encoding="utf-8")
    assert "plugins:" in text
    assert "model_gateway:" in text
    assert "agent_runtime:" in text
