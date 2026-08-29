#!/usr/bin/env python3
"""Environment health check. Run before deploying or in CI.

Usage:
    uv run nk doctor
    python -m scripts.doctor
Exits 0 if all checks pass, 1 if any fail.
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

_results: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, fix_hint: str = "") -> None:
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {name}")
    if not ok and fix_hint:
        print(f"         Fix: {fix_hint}")
    _results.append((name, ok, fix_hint))


def run_doctor(project_root: Path | None = None) -> bool:
    global _results
    _results = []
    root = project_root or Path.cwd()
    print("Running environment health checks...")

    for tool in ("git", "uv"):
        found = shutil.which(tool) is not None
        _check(f"{tool} installed", found, f"Install {tool}")

    ver = sys.version_info
    _check(f"Python {ver.major}.{ver.minor}", ver >= (3, 12), "Requires >=3.12")

    manifest = root / "platform.yaml"
    _check("platform.yaml exists", manifest.exists(), "Run generator first")

    modules: dict = {}
    if manifest.exists():
        try:
            import yaml

            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            modules = data.get("modules") or {}
            _check("platform.yaml parses", True)
        except Exception as exc:  # noqa: BLE001
            _check("platform.yaml parses", False, str(exc))

    # Package import smoke (package dir next to platform.yaml)
    pkg_name = None
    if manifest.exists():
        try:
            import yaml

            pkg_name = (yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}).get(
                "project",
            )
        except Exception:  # noqa: BLE001
            pkg_name = None
    if pkg_name:
        sys.path.insert(0, str(root))
        for mod_name in (
            f"{pkg_name}.settings",
            f"{pkg_name}.core.errors",
            f"{pkg_name}.cli",
        ):
            try:
                importlib.import_module(mod_name)
                _check(f"import {mod_name}", True)
            except ImportError as exc:
                _check(f"import {mod_name}", False, str(exc))

    if modules.get("redis") in (True, "True", "true"):
        _check(
            "redis module enabled (runtime reachability optional)",
            True,
            "Start compose via `uv run nk dev` when testing redis",
        )

    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    return passed == len(_results) and len(_results) > 0


if __name__ == "__main__":
    success = run_doctor()
    sys.exit(0 if success else 1)
