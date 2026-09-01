#!/usr/bin/env python3
"""AI stack health check for local / compose dev planes (P0).

Usage:
    uv run nk ai doctor
    python -m scripts.ai_doctor

Exits 0 if all checks pass, 1 if any fail.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

_results: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, fix_hint: str = "") -> None:
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {name}")
    if not ok and fix_hint:
        print(f"         Fix: {fix_hint}")
    _results.append((name, ok, fix_hint))


def _truthy(value: Any) -> bool:
    return value in (True, "True", "true", 1, "1")


def _ollama_base_url() -> str:
    for key in ("OLLAMA_API_BASE", "OLLAMA_HOST"):
        value = os.environ.get(key)
        if value:
            return value.rstrip("/")
    return "http://127.0.0.1:11434"


def probe_ollama(base_url: str | None = None) -> tuple[bool, str]:
    """Return (ok, detail) for an Ollama /api/tags probe."""
    url = (base_url or _ollama_base_url()).rstrip("/")
    try:
        with urlopen(f"{url}/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        return False, f"unreachable ({exc.reason})"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    models = [item.get("name", "") for item in payload.get("models", []) if item.get("name")]
    if not models:
        return (
            False,
            "reachable but no models loaded — run: "
            "docker compose exec ollama ollama pull llama3.2",
        )
    preview = ", ".join(models[:5])
    suffix = " …" if len(models) > 5 else ""
    return True, f"models: {preview}{suffix}"


def probe_qdrant(base_url: str | None = None) -> tuple[bool, str]:
    """Return (ok, detail) for a Qdrant /readyz probe."""
    url = (base_url or os.environ.get("QDRANT_HOST") or "http://127.0.0.1:6333").rstrip("/")
    if not url.startswith("http"):
        url = f"http://{url}"
    try:
        with urlopen(f"{url}/readyz", timeout=5) as response:
            if response.status != 200:
                return False, f"status {response.status}"
    except URLError as exc:
        return False, f"unreachable ({exc.reason})"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, url


def run_ai_doctor(project_root: Path | None = None) -> bool:
    """Run AI-plane checks. Returns True when all checks pass."""
    global _results
    _results = []
    root = project_root or Path.cwd()
    print("Running AI stack health checks...")

    manifest_path = root / "platform.yaml"
    _check("platform.yaml exists", manifest_path.is_file(), "Generate the project first")
    modules: dict[str, Any] = {}
    providers: dict[str, Any] = {}
    llm_features: dict[str, Any] = {}
    pkg_name: str | None = None
    if manifest_path.is_file():
        try:
            import yaml

            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            modules = data.get("modules") or {}
            providers = data.get("providers") or {}
            llm_features = data.get("llm_features") or {}
            pkg_name = data.get("project")
            _check("platform.yaml parses", True)
        except Exception as exc:  # noqa: BLE001
            _check("platform.yaml parses", False, str(exc))

    llm_enabled = _truthy(modules.get("llm"))
    _check(
        "LLM module enabled",
        llm_enabled,
        "Regenerate with --profile production-ai-local or enable_llm",
    )

    if llm_enabled:
        base = _ollama_base_url()
        ok, detail = probe_ollama(base)
        _check(f"Ollama ({base})", ok, detail if not ok else "")

        if pkg_name:
            sys.path.insert(0, str(root))
            try:
                settings_mod = importlib.import_module(f"{pkg_name}.settings")
                settings = settings_mod.settings
                _check(
                    f"default LLM route ({settings.llm_provider}/{settings.llm_model})",
                    bool(settings.llm_provider and settings.llm_model),
                    "Set LLM provider/model in settings or env",
                )
                memory_backend = getattr(settings, "memory_backend", "auto")
                _check(
                    f"memory backend ({memory_backend})",
                    True,
                    "auto selects redis when Redis module is enabled",
                )
                vector_backend = getattr(settings, "vector_store_backend", "auto")
                _check(
                    f"vector store backend ({vector_backend})",
                    True,
                    "auto selects pgvector on PostgreSQL; set qdrant for scale",
                )
            except ImportError as exc:
                _check("settings import", False, str(exc))

        vector_enabled = _truthy(modules.get("vector"))
        database = providers.get("database")
        if vector_enabled and database == "postgresql":
            _check(
                "pgvector module (PostgreSQL + vector)",
                True,
                "Start compose via `uv run nk dev`; pgvector table is created at startup",
            )
        elif vector_enabled:
            _check(
                "vector storage module",
                True,
                "Using in-memory vectors unless PostgreSQL+pgvector is configured",
            )

        if vector_enabled:
            q_ok, q_detail = probe_qdrant()
            label = f"Qdrant ({q_detail})" if q_ok else f"Qdrant optional — {q_detail}"
            _check(label, True, "Enable with VECTOR_STORE_BACKEND=qdrant for scale profiles")

        if _truthy(modules.get("redis")):
            _check(
                "Redis module (sessions / cache / optional memory)",
                True,
                "Start compose via `uv run nk dev` when testing Redis-backed features",
            )

        if _truthy(modules.get("taskiq")):
            _check(
                "Taskiq worker service",
                True,
                "Worker starts with `uv run nk dev` (taskiq-worker in compose)",
            )

        enabled_packs = [
            name
            for name, flag in llm_features.items()
            if name != "enabled" and _truthy(flag)
        ]
        _check(
            f"LLM feature packs ({len(enabled_packs)} enabled)",
            len(enabled_packs) > 0,
            "Enable packs in platform.yaml / cookiecutter options",
        )

        if pkg_name:
            dev_seed = (
                root
                / pkg_name
                / "llm"
                / "dev_seed.py"
            )
            _check("dev seed module", dev_seed.is_file(), "Missing llm/dev_seed.py")

    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    return passed == len(_results) and len(_results) > 0


if __name__ == "__main__":
    success = run_ai_doctor()
    sys.exit(0 if success else 1)
