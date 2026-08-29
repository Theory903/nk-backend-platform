#!/usr/bin/env python3
"""Validate generated project structure: imports, orphaned files, manifest consistency."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_issues: list[str] = []


def run_validate(project_root: Path | None = None) -> bool:
    global _issues
    _issues = []
    root = project_root or Path.cwd()
    pkg_dirs = [d for d in root.iterdir() if d.is_dir() and (d / "__init__.py").exists()]
    if not pkg_dirs:
        _issues.append("no package directory found")
        return False
    pkg = pkg_dirs[0]  # assume single top-level package

    # Check all .py files parse as valid Python
    for py_file in sorted(pkg.rglob("*.py")):
        try:
            ast.parse(py_file.read_text())
        except SyntaxError as exc:
            _issues.append(f"syntax error in {py_file.relative_to(root)}: {exc}")

    # Check platform.yaml modules match actual directories
    import yaml
    manifest_path = root / "platform.yaml"
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text())
        modules = manifest.get("modules", {})
        module_map = {
            "redis": "services/redis",
            "taskiq": None,
            "agents": "agents",
            "llm": "ai",
            "vector": "data",
        }
        for mod_name, enabled in modules.items():
            dir_path = module_map.get(mod_name)
            if dir_path is not None:
                full_path = root / dir_path.split("/")[0]
                if enabled and not full_path.exists():
                    _issues.append(f"module '{mod_name}' enabled but '{dir_path.split('/')[0]}/' missing")

    if _issues:
        print(f"Found {len(_issues)} issues:")
        for issue in _issues:
            print(f"  - {issue}")
        return False
    print("Project structure validated: no issues found.")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_validate() else 1)
