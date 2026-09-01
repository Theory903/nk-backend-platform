<!-- AI Platform OSS Map · updated 2026-09-01 · status: active -->

# NK AI Platform — OSS Reference Map

[← Master roadmap](ai-platform-roadmap.md)

**Clone all:** `./scripts/clone_ai_platform_refs.sh`  
**Regenerate manifest:** `python3 scripts/build_ai_platform_manifest.py`  
**Generated manifest:** `platform/oss_manifest.yaml` in generated projects

---

## Classification rules

| Type | Meaning |
|------|---------|
| `runtime` | Pip adapter; hidden execution engine |
| `adapter` | Optional backend behind NK interface |
| `protocol` | MCP / A2A SDK dependency |
| `reference` | Study only — no vendor copy |
| `skill` | Workflow patterns (gstack) |
| `evaluator` | Harness metric backend |
| `backend` | Infra service (Qdrant, SearXNG compose) |
| `research` | Autoresearch / optimization loops |
| `architecture_reference` | Shapes NK kernel design |

**License policy:** Prefer MIT/Apache-2.0 for dependencies. GPL/AGPL (e.g. SearXNG) → compose service or rewrite, never vendored into generated apps.

---

## Architecture references

| Repo | License | NK module | Phase |
|------|---------|-----------|-------|
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | MIT | `kernel/plugins/` | P21 |
| [garrytan/gstack](https://github.com/garrytan/gstack) | MIT | `skills/engineering/` | P22–P23 |

DeepSeek Harness: plugin + session + replay/fork. **Dev preview — reference only, no hard dependency.**

---

## Agent runtime

| Repo | Integration | pip | NK module |
|------|-------------|-----|-----------|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | adapter | `langgraph` | `runtime/graph/` |
| [huggingface/smolagents](https://github.com/huggingface/smolagents) | adapter | `smolagents` | `agents/code/` |
| [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) | reference | — | `agents/code/reference/` |

---

## Karpathy (reference + autoresearch)

| Repo | Priority | NK role |
|------|----------|---------|
| [autoresearch](https://github.com/karpathy/autoresearch) | 🔴 P26 | Experiment loop for harness evolution |
| [nanochat](https://github.com/karpathy/nanochat) | 🔴 P0 | Local-first stack reference |
| [nanoGPT](https://github.com/karpathy/nanoGPT) | 🟡 P2 | Training reference |
| [llm.c](https://github.com/karpathy/llm.c) | 🟡 P3 | Minimal LLM reference |
| microgpt (blog/nanochat) | 🟢 P3 | Minimal implementation principle |
| [llama2.c](https://github.com/karpathy/llama2.c) | 🟢 P4 | Inference reference |
| [micrograd](https://github.com/karpathy/micrograd) | 🟢 P4 | Autograd reference |
| [makemore](https://github.com/karpathy/makemore) | 🟢 P4 | Small-model reference |

**Principle:** Every NK subsystem has `production` + `minimal` paths (LangGraph vs LoopRuntime, Qdrant vs InMemory, etc.).

---

## RAG / vector / eval

| Repo | Type | pip |
|------|------|-----|
| [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | adapter | `haystack-ai` |
| [qdrant/qdrant-client](https://github.com/qdrant/qdrant-client) | backend | `qdrant-client` |
| pgvector (existing) | backend | `pgvector` |
| [explodinggradients/ragas](https://github.com/explodinggradients/ragas) | evaluator | `ragas` |

---

## Protocols

| Repo | pip | Role |
|------|-----|------|
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | `mcp` | Agent → tool |
| [a2aproject/a2a-python](https://github.com/a2aproject/a2a-python) | `a2a-sdk` | Agent → agent |

---

## Model / browser / search

| Repo | pip | NK module |
|------|-----|-----------|
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | `litellm` | `ai/gateway/adapters/litellm.py` |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | `browser-use` | `agents/browser/` |
| [searxng/searxng](https://github.com/searxng/searxng) | — (compose) | `tools/search/searxng.py` |

---

## Evaluation / optimization

| Repo | Integration |
|------|-------------|
| [harness/harness-evals](https://github.com/harness/harness-evals) | reference |
| [confident-ai/deepeval](https://github.com/confident-ai/deepeval) | adapter |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | CLI subprocess |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | optional adapter |

---

## Observability

| Repo | NK module |
|------|-----------|
| [open-telemetry/semantic-conventions](https://github.com/open-telemetry/semantic-conventions) | `observability/genai/spans.py` |

---

## Full reference tree

```text
NK OSS REFERENCE MAP
├── FOUNDATION — FastAPI, Pydantic, SQLAlchemy, Taskiq
├── MODEL — Ollama, LiteLLM, Karpathy (nanochat, autoresearch, …)
├── AGENTS — LangGraph, smolagents, OpenHands
├── SKILLS — gstack
├── ARCHITECTURE — DeepSeek Harness
├── RAG — Haystack, Qdrant, pgvector, Ragas, GraphRAG
├── TOOLS — MCP, A2A, SearXNG, Browser Use
├── EVALUATION — Harness Evals, DeepEval, Promptfoo
├── OPTIMIZATION — DSPy, autoresearch
└── OBSERVABILITY — OTel GenAI
```

---

## Optional pip extras (generated projects)

```bash
uv sync --extra ai-platform --extra ai-eval --extra browser
```

[← Master roadmap](ai-platform-roadmap.md)
