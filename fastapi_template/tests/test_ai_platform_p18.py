"""Tests for P18 AI security (injection, PII, poisoning, RAG boundary)."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
AGENTS = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "agents"


def test_p18_security_modules_exist() -> None:
    for name in (
        "security_pii.py",
        "security_poisoning.py",
        "security_rag.py",
        "security_loader.py",
        "security_manifest.yaml",
        "security_invariants.py",
    ):
        assert (AGENTS / name).is_file(), name


def test_security_pipeline_wires_pii_and_poisoning() -> None:
    text = (AGENTS / "security.py").read_text(encoding="utf-8")
    assert "inspect_tool_poisoning" in text
    assert "finalize_output" in text
    assert "PIIRedactor" in text
    assert "ToolPoisoningDefense" in text


def test_bootstrap_exposes_security_pipeline() -> None:
    text = (AGENTS / "bootstrap.py").read_text(encoding="utf-8")
    assert "build_security_pipeline" in text
    assert "security_pipeline" in text
    assert "build_sandbox_policy" in text


def test_rag_answer_uses_data_boundary() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "ai" / "knowledge" / "answer.py"
    ).read_text(encoding="utf-8")
    assert "wrap_retrieved_context" in text
    assert "format_retrieved_chunk" in text


def test_cli_security_audit_command() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "cli" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert "cmd_ai_security_audit" in text
    assert '"audit"' in text


def test_settings_security_manifest_override() -> None:
    text = (
        TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "settings.py"
    ).read_text(encoding="utf-8")
    assert "security_manifest_file" in text
