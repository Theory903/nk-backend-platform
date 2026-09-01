"""Generate NK-native LLM feature pack modules."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / (
    "fastapi_template/template/{{cookiecutter.project_name}}/{{cookiecutter.project_name}}/llm/features"
)

PACKS = {
    "chat_over_docs": {
        "meta": ("chat_over_docs", "Chat Over Documents", ("llm", "rag_traditional", "vector")),
        "tools": ["search_knowledge"],
        "route": "query",
        "uses_rag": True,
    },
    "agentic_rag": {
        "meta": ("agentic_rag", "Agentic RAG", ("llm", "rag_traditional", "vector", "agents")),
        "tools": ["plan_retrieval"],
        "route": "run",
        "uses_rag": True,
    },
    "deep_research": {
        "meta": ("deep_research", "Deep Research", ("llm", "agents")),
        "tools": ["outline_research", "summarize_notes"],
        "route": "research",
    },
    "data_analyst": {
        "meta": ("data_analyst", "Data Analyst", ("llm", "agents")),
        "tools": ["analyze_table"],
        "route": "analyze",
    },
    "starter_agents": {
        "meta": ("starter_agents", "Starter Agents", ("llm", "agents")),
        "tools": ["quick_answer"],
        "route": "ask",
    },
    "advanced_agents": {
        "meta": ("advanced_agents", "Advanced Agents", ("llm", "agents")),
        "tools": ["delegate_subtask"],
        "route": "team",
    },
    "mcp_assistant": {
        "meta": ("mcp_assistant", "MCP Assistant", ("llm", "agents")),
        "tools": [],
        "route": "status",
    },
    "memory_chat": {
        "meta": ("memory_chat", "Memory Chat", ("llm", "agents")),
        "tools": ["remember_fact"],
        "route": "chat",
    },
    "voice_multimodal": {
        "meta": ("voice_multimodal", "Voice & Multimodal", ("llm",)),
        "tools": ["describe_content"],
        "route": "describe",
    },
    "always_on": {
        "meta": ("always_on", "Always-On Agents", ("llm", "agents", "taskiq")),
        "tools": ["schedule_digest"],
        "route": "schedules",
    },
    "generative_ui": {
        "meta": ("generative_ui", "Generative UI", ("llm", "agents")),
        "tools": ["ui_component_spec"],
        "route": "ui-spec",
    },
    "structured_agents": {
        "meta": ("structured_agents", "Structured Agents", ("llm", "agents")),
        "tools": ["structured_extract"],
        "route": "extract",
    },
}

TEMPLATE = '''"""NK feature pack: {name}."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from {{{{cookiecutter.project_name}}}}.agents.tools import ToolRegistry, agent_tool
from {{{{cookiecutter.project_name}}}}.llm.features.base import FeaturePackMeta
from {{{{cookiecutter.project_name}}}}.llm.features.common.context import FeatureContext
from {{{{cookiecutter.project_name}}}}.llm.features.common.research import research_outline, summarize_text
{extra_imports}


class _Pack:
    meta = FeaturePackMeta(
        id="{pid}",
        name="{name}",
        requires={requires},
    )

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        ctx: FeatureContext | None = None,
    ) -> None:
{tool_body}

    def router(self) -> APIRouter:
        router = APIRouter(prefix="/{prefix}", tags=["llm-features"])

        class Payload(BaseModel):
            input: str = Field(min_length=1, max_length=100_000)

        @router.post("/{route}")
        async def _handle(payload: Payload, request: Request) -> dict[str, str]:
{handler_body}

        return router


PACK = _Pack()
'''


def _tool_lines(tools: list[str], uses_rag: bool) -> str:
    lines = []
    if "outline_research" in tools:
        lines.append('        @agent_tool("Create a markdown research outline for a topic")')
        lines.append("        async def outline_research(topic: str) -> str:")
        lines.append("            return await research_outline(topic)")
        lines.append("        registry.register(outline_research)")
    if "summarize_notes" in tools:
        lines.append('        @agent_tool("Summarize long notes or text")')
        lines.append("        async def summarize_notes(text: str) -> str:")
        lines.append("            return await summarize_text(text)")
        lines.append("        registry.register(summarize_notes)")
    if "quick_answer" in tools:
        lines.append('        @agent_tool("Answer a general question concisely")')
        lines.append("        async def quick_answer(question: str) -> str:")
        lines.append("            from {{cookiecutter.project_name}}.ai.gateway.router import get_router")
        lines.append("            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage")
        lines.append('            model = get_router().model_for(task="default")')
        lines.append("            reply = await model.complete([ModelMessage(role='user', content=question)])")
        lines.append("            return reply.content or ''")
        lines.append("        registry.register(quick_answer)")
    if "analyze_table" in tools:
        lines.append('        @agent_tool("Analyze CSV or tabular text and return insights")')
        lines.append("        async def analyze_table(table_text: str) -> str:")
        lines.append("            return await summarize_text(table_text, focus='data patterns and anomalies')")
        lines.append("        registry.register(analyze_table)")
    if "delegate_subtask" in tools:
        lines.append('        @agent_tool("Break a goal into numbered subtasks for a team agent")')
        lines.append("        async def delegate_subtask(goal: str) -> str:")
        lines.append("            return await research_outline(goal, sections=4)")
        lines.append("        registry.register(delegate_subtask)")
    if "remember_fact" in tools:
        lines.append('        @agent_tool("Store a short fact in the current thread memory keyspace")')
        lines.append("        async def remember_fact(fact: str) -> str:")
        lines.append('            return f"remembered: {fact[:500]}"')
        lines.append("        registry.register(remember_fact)")
    if "describe_content" in tools:
        lines.append('        @agent_tool("Describe text or transcript content for accessibility")')
        lines.append("        async def describe_content(content: str) -> str:")
        lines.append("            return await summarize_text(content, focus='visual and audio cues')")
        lines.append("        registry.register(describe_content)")
    if "schedule_digest" in tools:
        lines.append('        @agent_tool("Describe an always-on digest schedule payload")')
        lines.append("        async def schedule_digest(topic: str) -> str:")
        lines.append('            return f"digest scheduled for topic: {topic}"')
        lines.append("        registry.register(schedule_digest)")
    if "ui_component_spec" in tools:
        lines.append('        @agent_tool("Draft a UI component spec from a product requirement")')
        lines.append("        async def ui_component_spec(requirement: str) -> str:")
        lines.append("            return await research_outline(requirement, sections=3)")
        lines.append("        registry.register(ui_component_spec)")
    if "structured_extract" in tools:
        lines.append('        @agent_tool("Extract JSON-ready fields from unstructured text")')
        lines.append("        async def structured_extract(text: str, schema_hint: str = "") -> str:")
        lines.append("            from {{cookiecutter.project_name}}.ai.gateway.router import get_router")
        lines.append("            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage")
        lines.append('            model = get_router().model_for(task="reasoning")')
        lines.append("            prompt = f'Extract structured fields. Schema hint: {schema_hint or \"key-value pairs\"}. Return JSON only.'")
        lines.append("            reply = await model.complete([")
        lines.append("                ModelMessage(role='system', content=prompt),")
        lines.append("                ModelMessage(role='user', content=text[:30_000]),")
        lines.append("            ])")
        lines.append("            return reply.content or '{}'")
        lines.append("        registry.register(structured_extract)")
    if uses_rag or "search_knowledge" in tools or "plan_retrieval" in tools:
        lines.append('        @agent_tool("Search the knowledge base and return a cited answer")')
        lines.append("        async def search_knowledge(query: str) -> str:")
        lines.append("            if ctx is None or ctx.rag_service is None:")
        lines.append('                return "RAG service not configured"')
        lines.append("            from {{cookiecutter.project_name}}.platform.contracts import Scope")
        lines.append("            from {{cookiecutter.project_name}}.llm.features.common.rag import answer_with_citations, format_cited_answer")
        lines.append("            scope = Scope(principal_id='agent', organization_id='default')")
        lines.append("            response = await answer_with_citations(ctx.rag_service, query=query, scope=scope)")
        lines.append("            return format_cited_answer(response)")
        lines.append("        registry.register(search_knowledge)")
    if not lines:
        lines.append("        pass")
    return "\n".join(lines)


def _handler(uses_rag: bool, route: str) -> str:
    if uses_rag:
        return """            service = getattr(request.app.state, "rag_service", None)
            if service is None:
                raise HTTPException(status_code=503, detail="RAG service unavailable")
            from {{cookiecutter.project_name}}.platform.contracts import Scope
            from {{cookiecutter.project_name}}.llm.features.common.rag import answer_with_citations, format_cited_answer
            scope = getattr(request.state, "scope", None)
            if scope is None:
                scope = Scope(principal_id="http", organization_id="default")
            response = await answer_with_citations(service, query=payload.input, scope=scope)
            return {"output": format_cited_answer(response)}"""
    if route == "status":
        return '            return {"output": "MCP assistant ready; connect via agents/mcp_bridge"}'
    return """            from {{cookiecutter.project_name}}.ai.gateway.router import get_router
            from {{cookiecutter.project_name}}.platform.contracts import ModelMessage
            model = get_router().model_for(task="default")
            reply = await model.complete([ModelMessage(role="user", content=payload.input)])
            return {"output": reply.content or ""}"""


def main() -> None:
    for pid, spec in PACKS.items():
        pid_val, name, requires = spec["meta"]
        uses_rag = spec.get("uses_rag", False)
        extra = ""
        if uses_rag:
            extra = "from {{{{cookiecutter.project_name}}}}.llm.features.common.rag import answer_with_citations, format_cited_answer"
        content = TEMPLATE.format(
            pid=pid_val,
            name=name,
            requires=requires,
            prefix=pid.replace("_", "-"),
            route=spec["route"],
            extra_imports=extra,
            tool_body=_tool_lines(spec["tools"], uses_rag),
            handler_body=_handler(uses_rag, spec["route"]),
        )
        dest = ROOT / pid / "__init__.py"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print("wrote", dest)


if __name__ == "__main__":
    main()
