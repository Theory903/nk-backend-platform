"""Tests for P2 capability-based model gateway."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
GATEWAY = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "ai" / "gateway"


def test_gateway_p2_modules_exist() -> None:
    assert (GATEWAY / "capabilities.yaml").is_file()
    assert (GATEWAY / "capabilities.py").is_file()
    assert (GATEWAY / "budget.py").is_file()
    assert (GATEWAY / "semantic_cache.py").is_file()
    assert (GATEWAY / "runtime.py").is_file()


def test_capabilities_manifest_declares_chat_reasoning_fast() -> None:
    text = (GATEWAY / "capabilities.yaml").read_text(encoding="utf-8")
    assert "capabilities:" in text
    assert "chat:" in text
    assert "reasoning:" in text
    assert "task_aliases:" in text


def test_router_exports_capability_api() -> None:
    text = (GATEWAY / "router.py").read_text(encoding="utf-8")
    assert "for_capability" in text
    assert "model_for_capability" in text
    assert "BudgetEnforcingChatModel" in text


def test_settings_include_gateway_cache_fields() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "settings.py"
    ).read_text(encoding="utf-8")
    assert "llm_semantic_cache_enabled" in text
    assert "llm_capabilities_file" in text
