#!/usr/bin/env python3
"""Build llm/features/catalog.yaml from temp/awesome-llm-apps."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML required") from None

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "temp" / "awesome-llm-apps"
OUT = (
    REPO
    / "fastapi_template"
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "llm"
    / "features"
    / "catalog.yaml"
)

CATEGORY_TO_PACK = {
    "agent_skills": "coding_skills",
    "starter_ai_agents": "starter_agents",
    "advanced_ai_agents": "advanced_agents",
    "mcp_ai_agents": "mcp_assistant",
    "rag_tutorials": "chat_over_docs",
    "voice_ai_agents": "voice_multimodal",
    "always_on_agents": "always_on",
    "generative_ui_agents": "generative_ui",
    "advanced_llm_apps": "memory_chat",
    "ai_agent_framework_crash_course": "structured_agents",
}

PACK_META = {
    "coding_skills": {
        "name": "Coding Agent Skills",
        "module": "agents.skills",
        "requires": ["agents"],
    },
    "starter_agents": {
        "name": "Starter Agents",
        "module": "llm.features.starter_agents",
        "requires": ["llm", "agents"],
    },
    "advanced_agents": {
        "name": "Advanced Multi-Step Agents",
        "module": "llm.features.advanced_agents",
        "requires": ["llm", "agents"],
    },
    "mcp_assistant": {
        "name": "MCP Tool Assistant",
        "module": "llm.features.mcp_assistant",
        "requires": ["llm", "agents"],
    },
    "chat_over_docs": {
        "name": "Chat Over Documents (RAG)",
        "module": "llm.features.chat_over_docs",
        "requires": ["llm", "rag_traditional", "vector"],
    },
    "voice_multimodal": {
        "name": "Voice & Multimodal",
        "module": "llm.features.voice_multimodal",
        "requires": ["llm"],
    },
    "always_on": {
        "name": "Always-On Scheduled Agents",
        "module": "llm.features.always_on",
        "requires": ["llm", "agents", "taskiq"],
    },
    "generative_ui": {
        "name": "Generative UI Agents",
        "module": "llm.features.generative_ui",
        "requires": ["llm", "agents"],
    },
    "memory_chat": {
        "name": "Memory & Stateful Chat",
        "module": "llm.features.memory_chat",
        "requires": ["llm", "agents"],
    },
    "structured_agents": {
        "name": "Structured Agent Patterns",
        "module": "llm.features.structured_agents",
        "requires": ["llm", "agents"],
    },
    "agentic_rag": {
        "name": "Agentic RAG",
        "module": "llm.features.agentic_rag",
        "requires": ["llm", "rag_traditional", "vector", "agents"],
    },
    "data_analyst": {
        "name": "Data Analyst Agent",
        "module": "llm.features.data_analyst",
        "requires": ["llm", "agents"],
    },
    "deep_research": {
        "name": "Deep Research Agent",
        "module": "llm.features.deep_research",
        "requires": ["llm", "agents"],
    },
}

_ADVANCED_SUB = ("single_agent_apps", "multi_agent_apps", "agent_teams", "autonomous_game_playing_agent_apps")


def _slug(*parts: str) -> str:
    raw = "-".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "unknown"


def _iter_apps(category: str, root: Path):
    cat_root = root / category
    if not cat_root.is_dir():
        return
    if category == "advanced_ai_agents":
        for sub in _ADVANCED_SUB:
            sub_root = cat_root / sub
            if not sub_root.is_dir():
                continue
            for app_dir in sorted(sub_root.iterdir()):
                if app_dir.is_dir() and not app_dir.name.startswith("."):
                    yield sub, app_dir
        return
    for app_dir in sorted(cat_root.rglob("*")):
        if not app_dir.is_dir() or app_dir.name.startswith("."):
            continue
        if category == "agent_skills" and app_dir.parent != cat_root:
            if (app_dir / "SKILL.md").is_file():
                yield None, app_dir
            continue
        if app_dir.parent == cat_root and (
            list(app_dir.glob("*.py")) or (app_dir / "SKILL.md").exists() or (app_dir / "requirements.txt").exists()
        ):
            yield None, app_dir


def main() -> int:
    if not SOURCE.is_dir():
        print(f"Missing {SOURCE}", file=sys.stderr)
        return 1

    upstream: list[dict] = []
    pack_counts: dict[str, int] = {k: 0 for k in PACK_META}

    for category, pack_id in CATEGORY_TO_PACK.items():
        for sub, app_dir in _iter_apps(category, SOURCE):
            rel = app_dir.relative_to(SOURCE).as_posix()
            upstream.append(
                {
                    "id": _slug(category, sub or "", app_dir.name),
                    "name": app_dir.name,
                    "category": category,
                    "pack": pack_id,
                    "path": rel,
                }
            )
            pack_counts[pack_id] = pack_counts.get(pack_id, 0) + 1

    catalog = {
        "version": 1,
        "source": "temp/awesome-llm-apps",
        "pack_count": len(PACK_META),
        "upstream_count": len(upstream),
        "packs": {
            pid: {**meta, "upstream_templates": pack_counts.get(pid, 0)}
            for pid, meta in PACK_META.items()
        },
        "upstream": upstream,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"catalog: {len(upstream)} upstream → {len(PACK_META)} packs → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
