"""Map upstream LLM app patterns to NK extension points.

Full upstream catalog: ``llm/features/catalog.yaml`` (102 templates → 13 packs).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PatternTarget:
    """Where a pattern belongs in the NK platform."""

    pattern: str
    pack: str
    module: str
    register_via: str
    notes: str


PATTERNS: tuple[PatternTarget, ...] = (
    PatternTarget(
        "agent-skills",
        "coding_skills",
        "agents.skills",
        "agents/skills/<name>/SKILL.md + SkillLoader",
        "Coding-agent skills from upstream agent_skills/.",
    ),
    PatternTarget(
        "starter-agents",
        "starter_agents",
        "llm.features.starter_agents",
        "llm/features/starter_agents + @agent_tool",
        "Single-purpose agents (travel, finance, scraping, …).",
    ),
    PatternTarget(
        "advanced-agents",
        "advanced_agents",
        "llm.features.advanced_agents",
        "llm/features/advanced_agents + bounded runtime",
        "Multi-step and multi-agent upstream templates.",
    ),
    PatternTarget(
        "rag",
        "chat_over_docs",
        "llm.features.chat_over_docs",
        "ai/knowledge + llm/features/chat_over_docs",
        "All rag_tutorials and chat_with_X patterns.",
    ),
    PatternTarget(
        "agentic-rag",
        "agentic_rag",
        "llm.features.agentic_rag",
        "agents/agentic_rag.py + feature pack",
        "Agentic RAG tutorial cluster.",
    ),
    PatternTarget(
        "deep-research",
        "deep_research",
        "llm.features.deep_research",
        "common/research.py + feature pack",
        "Research planner / deep research agents.",
    ),
    PatternTarget(
        "data-analyst",
        "data_analyst",
        "llm.features.data_analyst",
        "llm/features/data_analyst tools",
        "CSV / Excel analysis agents.",
    ),
    PatternTarget(
        "mcp-agents",
        "mcp_assistant",
        "agents.mcp_bridge",
        "McpToolBridge.register_session",
        "All mcp_ai_agents templates.",
    ),
    PatternTarget(
        "memory-chat",
        "memory_chat",
        "llm.features.memory_chat",
        "agents/memory.py + feature pack",
        "Stateful chat and memory tutorials.",
    ),
    PatternTarget(
        "voice-multimodal",
        "voice_multimodal",
        "llm.features.voice_multimodal",
        "ai/multimodal + feature pack",
        "Voice and multimodal upstream agents.",
    ),
    PatternTarget(
        "always-on",
        "always_on",
        "llm.features.always_on",
        "Taskiq workers + feature pack",
        "Scheduled / always-on agents.",
    ),
    PatternTarget(
        "generative-ui",
        "generative_ui",
        "llm.features.generative_ui",
        "llm/features/generative_ui",
        "Generative UI agent templates.",
    ),
    PatternTarget(
        "structured-agents",
        "structured_agents",
        "llm.features.structured_agents",
        "llm/features/structured_agents",
        "OpenAI SDK crash course patterns (tools, handoffs, guardrails).",
    ),
)


def pattern_for(name: str) -> PatternTarget | None:
    key = name.strip().lower().replace("_", "-")
    for item in PATTERNS:
        if item.pattern == key:
            return item
    return None
