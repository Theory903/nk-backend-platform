"""Unit tests for evaluation adapters (P15)."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.agents.evaluation import EvalCase
from {{cookiecutter.project_name}}.agents.evaluation.adapters import get_adapter, list_adapters
from {{cookiecutter.project_name}}.agents.evaluation.adapters.native import NativeAdapter
from {{cookiecutter.project_name}}.agents.evaluation.adapters.promptfoo import PromptfooAdapter


def test_list_adapters_includes_native() -> None:
    names = {item.name for item in list_adapters()}
    assert "native" in names
    assert "harness" in names


def test_get_adapter_native() -> None:
    adapter = get_adapter("native")
    assert isinstance(adapter, NativeAdapter)


def test_unknown_adapter_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("not-real")


@pytest.mark.asyncio
async def test_native_adapter_runs_cases() -> None:
    cases = [EvalCase(name="a", input="hi", expected_contains=("hello",))]

    async def runner(_: str) -> dict[str, str]:
        return {"output": "hello world", "tools": []}

    report = await NativeAdapter().run(cases, runner)
    assert report.total == 1
    assert report.passed == 1


def test_promptfoo_export_writes_yaml(tmp_path) -> None:
    cases = [EvalCase(name="x", input="test", expected_contains=("NK",))]
    out = PromptfooAdapter.export_cases(cases, tmp_path / "promptfoo.yaml")
    assert out.is_file()
    assert "NK" in out.read_text(encoding="utf-8")
