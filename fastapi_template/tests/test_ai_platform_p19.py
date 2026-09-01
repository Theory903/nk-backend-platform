"""Tests for P19 OTel GenAI spans and cost/latency metrics."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)
PKG = TEMPLATE_ROOT / "{{cookiecutter.project_name}}"
GENAI = PKG / "observability" / "genai"


def test_p19_genai_modules_exist() -> None:
    for name in (
        "spans.py",
        "metrics.py",
        "instrumentation.py",
        "__init__.py",
    ):
        assert (GENAI / name).is_file(), name


def test_genai_spans_use_semantic_attributes() -> None:
    text = (GENAI / "spans.py").read_text(encoding="utf-8")
    for token in (
        "gen_ai.operation.name",
        "gen_ai.system",
        "gen_ai.request.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.tool.name",
        "gen_ai.agent.run",
    ):
        assert token in text


def test_router_wraps_instrumented_model() -> None:
    text = (PKG / "ai" / "gateway" / "router.py").read_text(encoding="utf-8")
    assert "InstrumentedChatModel" in text


def test_tool_gateway_records_genai_tool_metrics() -> None:
    text = (PKG / "agents" / "tool_gateway.py").read_text(encoding="utf-8")
    assert "tool_invoke_span" in text
    assert "record_tool_invoke" in text


def test_loop_uses_agent_run_span() -> None:
    text = (PKG / "agents" / "loop.py").read_text(encoding="utf-8")
    assert "agent_run_span" in text
    assert "record_agent_step" in text


def test_operations_metrics_genai_histograms() -> None:
    text = (PKG / "operations" / "metrics.py").read_text(encoding="utf-8")
    assert "llm_request_duration" in text
    assert "genai_tool_duration" in text
    assert "record_llm_latency" in text
    assert "record_genai_tool" in text


def test_cli_ai_metrics_command() -> None:
    text = (PKG / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert "cmd_ai_metrics" in text
    assert '"metrics"' in text
