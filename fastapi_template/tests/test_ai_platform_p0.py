"""Tests for P0 AI dev plane (dev_seed + ai_doctor)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "{{cookiecutter.project_name}}"
)


def test_dev_seed_module_exists() -> None:
    path = TEMPLATE_ROOT / "{{cookiecutter.project_name}}" / "llm" / "dev_seed.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "seed_dev_plane" in text
    assert "demo-user" in text


def test_ai_doctor_script_exists() -> None:
    path = TEMPLATE_ROOT / "scripts" / "ai_doctor.py"
    assert path.is_file()
    assert "probe_ollama" in path.read_text(encoding="utf-8")


def test_compose_includes_ollama_when_llm_enabled() -> None:
    compose = (TEMPLATE_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "ollama:" in compose
    assert "OLLAMA_API_BASE" in compose
    assert "{{cookiecutter.project_name}}-ollama-data" in compose


def test_dev_compose_exposes_ollama_port() -> None:
    dev = (TEMPLATE_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
    assert "NK_OLLAMA_PORT" in dev


def test_probe_ollama_reports_missing_models() -> None:
    import json
    from io import BytesIO

    sys_path = TEMPLATE_ROOT
    import sys

    sys.path.insert(0, str(sys_path))
    from scripts.ai_doctor import probe_ollama

    payload = json.dumps({"models": []}).encode("utf-8")

    class _Response:
        def read(self) -> bytes:
            return payload

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with patch("scripts.ai_doctor.urlopen", return_value=_Response()):
        ok, detail = probe_ollama("http://127.0.0.1:11434")
    assert ok is False
    assert "no models" in detail


def test_run_ai_doctor_skips_llm_checks_without_module(tmp_path: Path) -> None:
    import sys

    manifest = {
        "project": "demo",
        "modules": {"llm": False},
    }
    (tmp_path / "platform.yaml").write_text(
        yaml.safe_dump(manifest),
        encoding="utf-8",
    )
    sys.path.insert(0, str(TEMPLATE_ROOT))
    from scripts.ai_doctor import run_ai_doctor

    ok = run_ai_doctor(tmp_path)
    assert ok is False
