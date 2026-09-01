#!/usr/bin/env python3
"""Build categorized OSS → NK AI platform manifest."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OSS = ROOT / "temp" / "oss"
OUT = (
    ROOT
    / "fastapi_template"
    / "template"
    / "{{cookiecutter.project_name}}"
    / "{{cookiecutter.project_name}}"
    / "platform"
    / "oss_manifest.yaml"
)

# type: runtime | adapter | protocol | reference | skill | evaluator | backend | research | architecture_reference
ENTRIES: list[dict[str, str]] = [
    # ── Architecture references ───────────────────────────────────────────
    {
        "id": "deepseek-harness",
        "repo": "deepseek-ai/deepseek-harness",
        "category": "architecture_reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "kernel/plugins/",
        "priority": "P21",
        "use": "Plugin kernel, session events, replay/fork/resume (dev preview — pin as reference only)",
    },
    {
        "id": "gstack",
        "repo": "garrytan/gstack",
        "category": "skill",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "skills/engineering/",
        "priority": "P22-P23",
        "use": "Engineering skill workflows (review, QA, ship, retro) — NK-native SKILL.md equivalents",
    },
    # ── Agent runtime ───────────────────────────────────────────────────────
    {
        "id": "langgraph",
        "repo": "langchain-ai/langgraph",
        "category": "runtime",
        "integration": "adapter",
        "license": "MIT",
        "pip": "langgraph>=1.0,<2",
        "nk_module": "runtime/graph/",
        "priority": "P3",
        "use": "Graph/supervisor/durable execution engine (hidden)",
    },
    {
        "id": "smolagents",
        "repo": "huggingface/smolagents",
        "category": "runtime",
        "integration": "adapter",
        "license": "Apache-2.0",
        "pip": "smolagents",
        "nk_module": "agents/code/lightweight.py",
        "priority": "P11",
        "use": "Lightweight/code agent adapter",
    },
    {
        "id": "OpenHands",
        "repo": "All-Hands-AI/OpenHands",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "agents/code/reference/",
        "priority": "P11",
        "use": "Code-agent sandbox patterns",
    },
    # ── Karpathy ────────────────────────────────────────────────────────────
    {
        "id": "autoresearch",
        "repo": "karpathy/autoresearch",
        "category": "research",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "research/experiments/",
        "priority": "P26-P27",
        "use": "Autonomous experiment loop: hypothesis → mutate → run → eval → keep/revert",
    },
    {
        "id": "nanochat",
        "repo": "karpathy/nanochat",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "profiles/production-ai-local",
        "priority": "P0",
        "use": "Local-first ChatGPT-like stack reference",
    },
    {
        "id": "nanoGPT",
        "repo": "karpathy/nanoGPT",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "research/reference/",
        "priority": "P2",
        "use": "Training/finetuning reference",
    },
    {
        "id": "llm.c",
        "repo": "karpathy/llm.c",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "research/reference/",
        "priority": "P3",
        "use": "Minimal LLM training/inference reference",
    },
    {
        "id": "llama2.c",
        "repo": "karpathy/llama2.c",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "research/reference/",
        "priority": "P4",
        "use": "Minimal inference reference",
    },
    {
        "id": "micrograd",
        "repo": "karpathy/micrograd",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "research/reference/",
        "priority": "P4",
        "use": "Autograd educational reference",
    },
    {
        "id": "makemore",
        "repo": "karpathy/makemore",
        "category": "reference",
        "integration": "reference",
        "license": "MIT",
        "pip": "",
        "nk_module": "research/reference/",
        "priority": "P4",
        "use": "Small-model experimentation reference",
    },
    {
        "id": "microgpt",
        "repo": "karpathy/microgpt (blog)",
        "category": "reference",
        "integration": "reference",
        "license": "n/a",
        "pip": "",
        "nk_module": "research/reference/",
        "priority": "P3",
        "use": "Minimal GPT implementation principle — no standalone repo; see nanochat",
    },
    # ── RAG / vector ────────────────────────────────────────────────────────
    {
        "id": "haystack",
        "repo": "deepset-ai/haystack",
        "category": "adapter",
        "integration": "adapter",
        "license": "Apache-2.0",
        "pip": "haystack-ai",
        "nk_module": "rag/adapters/haystack.py",
        "priority": "P5",
        "use": "Optional complex RAG pipeline backend",
    },
    {
        "id": "qdrant-client",
        "repo": "qdrant/qdrant-client",
        "category": "backend",
        "integration": "adapter",
        "license": "Apache-2.0",
        "pip": "qdrant-client",
        "nk_module": "rag/adapters/qdrant_store.py",
        "priority": "P1",
        "use": "Scale vector backend",
    },
    {
        "id": "ragas",
        "repo": "explodinggradients/ragas",
        "category": "evaluator",
        "integration": "adapter",
        "license": "Apache-2.0",
        "pip": "ragas",
        "nk_module": "harness/evaluators/ragas.py",
        "priority": "P15",
        "use": "RAG evaluation metrics",
    },
    # ── Protocols ───────────────────────────────────────────────────────────
    {
        "id": "python-sdk-mcp",
        "repo": "modelcontextprotocol/python-sdk",
        "category": "protocol",
        "integration": "dependency",
        "license": "MIT",
        "pip": "mcp",
        "nk_module": "protocols/mcp/",
        "priority": "P4",
        "use": "MCP client/server",
    },
    {
        "id": "a2a-python",
        "repo": "a2aproject/a2a-python",
        "category": "protocol",
        "integration": "dependency",
        "license": "Apache-2.0",
        "pip": "a2a-sdk",
        "nk_module": "protocols/a2a/",
        "priority": "P4/P8",
        "use": "Agent-to-agent protocol",
    },
    # ── Model gateway ───────────────────────────────────────────────────────
    {
        "id": "litellm",
        "repo": "BerriAI/litellm",
        "category": "adapter",
        "integration": "adapter",
        "license": "MIT",
        "pip": "litellm",
        "nk_module": "ai/gateway/adapters/litellm.py",
        "priority": "P2",
        "use": "Multi-provider routing and cost",
    },
    # ── Browser / tools ─────────────────────────────────────────────────────
    {
        "id": "browser-use",
        "repo": "browser-use/browser-use",
        "category": "runtime",
        "integration": "adapter",
        "license": "MIT",
        "pip": "browser-use",
        "nk_module": "agents/browser/",
        "priority": "P10",
        "use": "Browser agent (sandboxed)",
    },
    {
        "id": "searxng",
        "repo": "searxng/searxng",
        "category": "backend",
        "integration": "infra_service",
        "license": "AGPL-3.0",
        "pip": "",
        "nk_module": "tools/search/searxng.py",
        "priority": "P12",
        "use": "Self-hosted search (compose service, not vendored)",
    },
    # ── Evaluation ──────────────────────────────────────────────────────────
    {
        "id": "deepeval",
        "repo": "confident-ai/deepeval",
        "category": "evaluator",
        "integration": "adapter",
        "license": "Apache-2.0",
        "pip": "deepeval",
        "nk_module": "harness/evaluators/deepeval.py",
        "priority": "P15",
        "use": "Agent evaluation",
    },
    {
        "id": "harness-evals",
        "repo": "harness/harness-evals",
        "category": "evaluator",
        "integration": "reference",
        "license": "Apache-2.0",
        "pip": "",
        "nk_module": "harness/evaluators/harness.py",
        "priority": "P15",
        "use": "Trajectory evaluation dimensions",
    },
    {
        "id": "promptfoo",
        "repo": "promptfoo/promptfoo",
        "category": "evaluator",
        "integration": "reference_cli",
        "license": "MIT",
        "pip": "",
        "nk_module": "harness/adapters/promptfoo.py",
        "priority": "P15/P18",
        "use": "Red team / prompt regression CLI",
    },
    {
        "id": "dspy",
        "repo": "stanfordnlp/dspy",
        "category": "research",
        "integration": "adapter",
        "license": "MIT",
        "pip": "dspy",
        "nk_module": "research/optimization/dspy.py",
        "priority": "P27",
        "use": "Optional prompt/program optimization",
    },
    # ── Observability ───────────────────────────────────────────────────────
    {
        "id": "semantic-conventions",
        "repo": "open-telemetry/semantic-conventions",
        "category": "reference",
        "integration": "reference_spec",
        "license": "Apache-2.0",
        "pip": "",
        "nk_module": "observability/genai/spans.py",
        "priority": "P19",
        "use": "OTel GenAI semantic conventions",
    },
]


def _cloned(entry_id: str) -> bool:
    if not OSS.is_dir():
        return False
    needle = entry_id.replace("-", "_").lower()
    for folder in OSS.iterdir():
        if folder.name.replace("-", "_").lower() == needle:
            return True
        if folder.name.lower() == entry_id.lower():
            return True
    return (OSS / entry_id).is_dir()


def main() -> None:
    lines = [
        "# NK AI Platform — OSS manifest (generated)",
        "# Regenerate: scripts/build_ai_platform_manifest.py",
        "# Clone refs: scripts/clone_ai_platform_refs.sh",
        "",
        "classification_rules:",
        "  - runtime: pip adapter, hidden engine",
        "  - adapter: optional backend behind NK interface",
        "  - protocol: MCP/A2A SDK dependencies",
        "  - reference: study only, no vendor copy",
        "  - skill: workflow patterns (gstack)",
        "  - evaluator: harness backends",
        "  - backend: infra (Qdrant, SearXNG compose)",
        "  - research: autoresearch, optimization loops",
        "  - architecture_reference: shapes NK kernel design",
        "",
        "repositories:",
    ]
    for entry in ENTRIES:
        lines.append(f"  {entry['id']}:")
        lines.append(f"    repo: {entry['repo']}")
        lines.append(f"    category: {entry['category']}")
        lines.append(f"    integration: {entry['integration']}")
        lines.append(f"    license: {entry['license']}")
        if entry["pip"]:
            lines.append(f"    pip: \"{entry['pip']}\"")
        lines.append(f"    nk_module: {entry['nk_module']}")
        lines.append(f"    phase: {entry['priority']}")
        lines.append(f"    cloned: {str(_cloned(entry['id'])).lower()}")
        lines.append(f"    use: \"{entry['use']}\"")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)
    print(json.dumps({"entries": len(ENTRIES), "oss_dir": str(OSS)}, indent=2))


if __name__ == "__main__":
    main()
