---
id: ai-knowledge-agents
title: AI, knowledge, and agents
description: Retrieval, answering, and bounded agent capabilities in AI profiles.
---

[← INDEX](../INDEX.md)

AI capabilities are enabled progressively:

- `ai-saas` adds model providers, embeddings, vector storage, and traditional
  retrieval-augmented generation;
- `agentic` adds the bounded runtime, tool/MCP integration, approvals, memory,
  and GraphRAG;
- `fintech` does not imply AI capabilities.

The generated `platform.yaml` is the authoritative summary for one generated
project.

## Provider boundary

Model and embedding access uses protocols and adapters under
`ai/providers/`, `ai/llm.py`, and `ai/gateway/`. The template does not provide
credentials, a model-serving fleet, or a guarantee that an arbitrary provider
is available. Configure provider routing and versions in the generated
application and record them for reproducible evaluations.

## Knowledge lifecycle

The knowledge path is:

```text
source → normalized document → chunks → embeddings/index
→ authorized retrieval → ranked context → cited answer or abstention
```

`ai/knowledge/ingestion.py` supports text, URL, PDF, and DOCX normalization.
Documents and chunks preserve source identity and content hashes. URL loading
requires HTTP(S), blocks credentials in URLs, and rejects private, loopback,
and link-local targets.

Retrieval and answer composition live in:

- `ai/knowledge/retrieval.py` — retrieval provider contract;
- `ai/knowledge/ranking.py` — ranking support;
- `ai/knowledge/access.py` — scope and ACL filtering;
- `ai/knowledge/answer.py` — answer envelope, citations, cache, and abstention;
- `ai/knowledge/lifecycle.py` — document/version lifecycle;
- `ai/knowledge/vector_store.py` and `pgvector_store.py` — vector adapters;
- `ai/knowledge/graph.py` — graph retrieval adapter.

## Answer contract

`RAGAnswerService` accepts an explicit tenant scope, retrieval limits, score
threshold, model version, prompt version, and knowledge version. It returns:

- an answer only from retrieved evidence;
- citations containing chunk, document, source, version, and score;
- an explicit abstention when no authorized evidence meets the threshold;
- freshness metadata, usage, and cache status.

The `/api/v1/answers` route is available when traditional RAG is enabled.
Exact request and response schemas come from the generated OpenAPI document.

## Bounded agent runtime

The `agentic` profile provides an Observe → Reason → Act → Verify state
machine. `agents/runtime.py` enforces:

- maximum cycles and retries;
- cooperative cancellation;
- optional approvals before actions;
- an explicit action executor; pending actions fail closed if none is configured;
- checkpoint save/load;
- post-condition verification;
- action IDs to avoid replaying completed actions after resume.

Agent routes are composed by `web/api/agent_protocol.py`, with
`/api/v1/runs`, streaming, thread state, and optional MCP endpoints. Tools
must be explicitly registered and scoped. The generated MCP surface exposes
only read-only `health` and `build_info` tools by default. Runtime limits are
safety controls, not a substitute for provider-side or network-side policy.

## Evaluation and governance

Use `nk eval`, `scripts/eval.py`, `agents/evaluation/`, and
`tests/evals/golden.yaml` to run application-specific checks. Track model,
prompt, tool, and knowledge versions. A passing fixture suite is not evidence
of safety for new tools, tenants, models, or sensitive data; enable regression
and red-team gates where the deployment requires them.

## Reliability boundaries

- The default graph adapter is in-memory unless replaced.
- Checkpoint durability depends on the configured state store and database.
- Provider/model wiring must be tested with the selected production adapter.
- ACL filtering must be tested with tenant and authorization fixtures.
- Do not ingest private network URLs or credentials-bearing URLs.

## Evidence

- RAG endpoint: generated `web/api/knowledge.py`
- Agent endpoint: generated `web/api/agent_protocol.py`
- Runtime: generated `agents/runtime.py`
- Security: generated `agents/security.py` and `agents/guardrails.py`
- Tests: generated `tests/test_rag_answer.py`,
  `test_agent_runtime_contract.py`, `test_agent_security.py`, and
  `test_evaluation_governance.py`

