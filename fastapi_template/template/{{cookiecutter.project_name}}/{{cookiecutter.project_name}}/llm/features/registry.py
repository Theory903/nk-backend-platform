"""Discover and enable LLM feature packs from platform.yaml + catalog."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.llm.features.base import FeaturePack, FeaturePackMeta
from {{cookiecutter.project_name}}.llm.features.common.context import FeatureContext

_CATALOG_PATH = Path(__file__).with_name("catalog.yaml")

# NK-native pack modules (one per upstream category cluster).
_PACK_MODULES: dict[str, str] = {
    "coding_skills": "{{cookiecutter.project_name}}.agents.skills.factory",
    "chat_over_docs": "{{cookiecutter.project_name}}.llm.features.chat_over_docs",
    "agentic_rag": "{{cookiecutter.project_name}}.llm.features.agentic_rag",
    "deep_research": "{{cookiecutter.project_name}}.llm.features.deep_research",
    "data_analyst": "{{cookiecutter.project_name}}.llm.features.data_analyst",
    "starter_agents": "{{cookiecutter.project_name}}.llm.features.starter_agents",
    "advanced_agents": "{{cookiecutter.project_name}}.llm.features.advanced_agents",
    "mcp_assistant": "{{cookiecutter.project_name}}.llm.features.mcp_assistant",
    "memory_chat": "{{cookiecutter.project_name}}.llm.features.memory_chat",
    "voice_multimodal": "{{cookiecutter.project_name}}.llm.features.voice_multimodal",
    "always_on": "{{cookiecutter.project_name}}.llm.features.always_on",
    "generative_ui": "{{cookiecutter.project_name}}.llm.features.generative_ui",
    "structured_agents": "{{cookiecutter.project_name}}.llm.features.structured_agents",
}

_DEFAULT_ENABLED: dict[str, bool] = {
    "chat_over_docs": {% if cookiecutter.enable_rag_traditional in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "agentic_rag": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] and cookiecutter.enable_rag_traditional in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "deep_research": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "data_analyst": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "starter_agents": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "advanced_agents": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "mcp_assistant": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "memory_chat": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "voice_multimodal": {% if cookiecutter.enable_llm in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "always_on": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] and cookiecutter.enable_taskiq in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "generative_ui": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "structured_agents": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
    "coding_skills": {% if cookiecutter.enable_agents in [True, "True", "true", 1, "1"] %}True{% else %}False{% endif %},
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    if not _CATALOG_PATH.is_file():
        return {"packs": {}, "upstream": []}
    return yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}


def _pack_enabled(pack_id: str, manifest: dict[str, Any] | None) -> bool:
    features = (manifest or {}).get("llm_features") or {}
    if pack_id in features:
        return bool(features[pack_id])
    return _DEFAULT_ENABLED.get(pack_id, False)


def _requirements_met(pack_id: str, manifest: dict[str, Any] | None) -> bool:
    catalog = load_catalog()
    pack_info = (catalog.get("packs") or {}).get(pack_id) or {}
    modules = manifest.get("modules") if manifest else {}
    for req in pack_info.get("requires") or []:
        if req == "taskiq":
            if not (modules or {}).get("taskiq"):
                return False
        elif not (modules or {}).get(req):
            return False
    return True


def _load_pack_impl(pack_id: str) -> FeaturePack | None:
    if pack_id == "coding_skills":
        return None  # skills wired separately via SkillLoader
    module_path = _PACK_MODULES.get(pack_id)
    if not module_path:
        return None
    module = importlib.import_module(module_path)
    return getattr(module, "PACK", None)


def enabled_packs(manifest: dict[str, Any] | None = None) -> tuple[FeaturePack, ...]:
    catalog = load_catalog()
    packs: list[FeaturePack] = []
    for pack_id in sorted((catalog.get("packs") or {}).keys()):
        if not _pack_enabled(pack_id, manifest):
            continue
        if not _requirements_met(pack_id, manifest):
            continue
        impl = _load_pack_impl(pack_id)
        if impl is not None:
            packs.append(impl)
    return tuple(packs)


def list_packs(manifest: dict[str, Any] | None = None) -> list[FeaturePackMeta]:
    catalog = load_catalog()
    result: list[FeaturePackMeta] = []
    for pack_id, info in sorted((catalog.get("packs") or {}).items()):
        result.append(
            FeaturePackMeta(
                id=pack_id,
                name=str(info.get("name") or pack_id),
                requires=tuple(info.get("requires") or ()),
                upstream_templates=int(info.get("upstream_templates") or 0),
            )
        )
    return result


def get_pack(pack_id: str) -> FeaturePack:
    impl = _load_pack_impl(pack_id)
    if impl is None:
        raise KeyError(pack_id)
    return impl


def register_feature_tools(
    registry: ToolRegistry,
    *,
    manifest: dict[str, Any] | None = None,
    ctx: FeatureContext | None = None,
) -> list[str]:
    """Register tools from all enabled packs; return tool names added."""
    added: list[str] = []
    context = ctx or FeatureContext()
    for pack in enabled_packs(manifest):
        before = set(registry.names())
        pack.register_tools(registry, ctx=context)
        added.extend(name for name in registry.names() if name not in before)
    return added
