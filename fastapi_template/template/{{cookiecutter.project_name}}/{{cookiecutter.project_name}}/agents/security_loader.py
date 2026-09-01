"""Load AI security manifest and build SecurityPipeline (P18)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.agents.security import SecurityPipeline, ToolPolicy
from {{cookiecutter.project_name}}.agents.security_pii import PIIRedactor
from {{cookiecutter.project_name}}.agents.security_poisoning import ToolPoisoningDefense
from {{cookiecutter.project_name}}.agents.sandbox import SandboxPolicy
from {{cookiecutter.project_name}}.settings import settings

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_MANIFEST = _PACKAGE_DIR / "security_manifest.yaml"


@dataclass(frozen=True, slots=True)
class SecurityManifest:
    redact_pii_in_context: bool = True
    redact_pii_in_output: bool = True
    scan_tool_poisoning: bool = True
    rag_data_boundary: bool = True
    rag_sanitize_chunks: bool = True
    failed_approval_is_denial: bool = True
    sandbox_enabled: bool = False
    sandbox_allowed_commands: frozenset[str] = frozenset()


def _manifest_file() -> Path:
    override = getattr(settings, "security_manifest_file", None)
    if override:
        path = Path(override)
        if path.is_file():
            return path
    for candidate in (Path.cwd() / "agents" / "security_manifest.yaml", _DEFAULT_MANIFEST):
        if candidate.is_file():
            return candidate
    return _DEFAULT_MANIFEST


def load_security_manifest() -> SecurityManifest:
    path = _manifest_file()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pii = payload.get("pii") or {}
    poisoning = payload.get("tool_poisoning") or {}
    rag = payload.get("rag") or {}
    approval = payload.get("approval") or {}
    sandbox = payload.get("sandbox") or {}
    return SecurityManifest(
        redact_pii_in_context=bool(pii.get("redact_in_context", True)),
        redact_pii_in_output=bool(pii.get("redact_in_output", True)),
        scan_tool_poisoning=bool(poisoning.get("scan_on_invoke", True)),
        rag_data_boundary=bool(rag.get("data_boundary", True)),
        rag_sanitize_chunks=bool(rag.get("sanitize_chunks", True)),
        failed_approval_is_denial=bool(approval.get("failed_is_denial", True)),
        sandbox_enabled=bool(sandbox.get("enabled", False)),
        sandbox_allowed_commands=frozenset(
            str(item) for item in (sandbox.get("allowed_commands") or [])
        ),
    )


def build_security_pipeline(
    *,
    tool_policy: ToolPolicy | None = None,
    manifest: SecurityManifest | None = None,
) -> SecurityPipeline:
    """Compose the security pipeline from manifest defaults."""
    loaded = manifest or load_security_manifest()
    return SecurityPipeline(
        tool_policy=tool_policy or ToolPolicy(),
        pii_redactor=PIIRedactor(),
        tool_poisoning=ToolPoisoningDefense(),
        manifest=loaded,
    )


def build_sandbox_policy(manifest: SecurityManifest | None = None) -> SandboxPolicy | None:
    """Return sandbox policy when enabled in manifest; pass to LocalSandbox.execute()."""
    loaded = manifest or load_security_manifest()
    if not loaded.sandbox_enabled:
        return None
    return SandboxPolicy(allowed_commands=loaded.sandbox_allowed_commands)


__all__ = [
    "SecurityManifest",
    "build_sandbox_policy",
    "build_security_pipeline",
    "load_security_manifest",
]
