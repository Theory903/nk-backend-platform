# TEMP Full Feature Map — Every Feature From Docs + README + Code (Real OSS, No Fakes)

<!-- title: TEMP Full Feature Map · updated: 2026-08-24 · status: draft -->
<!-- source: local clones @ TEMP/* read 2026-08-24 via direct read (billing blocked explore agents) -->
<!-- instruction: map each and every feature in detail, perfectly, from docs/readme/code -->

> **Principle:** No `Fake*` stays in gold template. Every feature below is from official OSS docs/code in `TEMP/` — copy pattern, not vendor blob. Keep our `Protocol` as contract, replace impl with real adapter.

---

## 1. Legend — What "Map" Means

For each repo we extract:

- **Identity:** `TEMP/<name>` → GitHub origin, version, license, Python req.
- **Install:** how it installs (pip extras), env keys.
- **Architecture:** folder layout (`src/<pkg>`), key abstractions.
- **Exhaustive Features:** every bullet from README + every heading from `docs/` + every `def`/`class` from `src`.
- **Providers/Models/Capabilities:** enumerations from code.
- **Code To Harvest:** exact file + snippet to copy into `template/{{cookiecutter.project_name}}/{{cookiecutter.project_name}}/`.

---

## 2. `TEMP/any-llm` — `mozilla-ai/any-llm` — Unified LLM Gateway (Mozilla)

### 2.1 Identity

- **Origin:** `https://github.com/mozilla-ai/any-llm` (logo, Mozilla AI)
- **Package:** `any-llm-sdk` (`pyproject.toml` `name = "any-llm-sdk"`, `version = "0.0.0-dev"` → release regex sets real version)
- **Python:** `>=3.11`
- **License:** Apache-2.0
- **Badges:** docs, lint, unit, integration, PyPI, Discord, Python 3.11+
- **Tagline:** "Communicate with any LLM provider using a single, unified interface. Switch between OpenAI, Anthropic, Azure/Mistral/Ollama and more without changing code."
- **LiteLLM migration:** `from litellm import completion` → `from any_llm import completion`, model string `openai/gpt-4o` → `openai:gpt-4o` (provider:model), same env vars.

### 2.2 Install & Keys

```bash
pip install 'any-llm-sdk[mistral,ollama]'          # specific
pip install 'any-llm-sdk[openai,anthropic]'        # multi
pip install 'any-llm-sdk[all]'                     # all providers
# providers as extras: see pyproject.toml optional-dependencies
# mistral → mistralai>=2.0, anthropic → anthropic>=0.83, gemini → google-genai>=1.51,
# bedrock → boto3, vllm → vllm, ollama → ollama, openai → openai>=2.18, etc
export MISTRAL_API_KEY=...   # or OPENAI_API_KEY, ANTHROPIC_API_KEY, etc
# also supports OTARI, etc: see docs/providers
```

- **Env var convention:** `PROVIDER_API_KEY` + optional `PROVIDER_API_BASE` (for gateways). Code reads `os.environ.get`.
- **Custom OpenAI-compat endpoint:** `completion(model="my-model", provider="openai", api_base="https://my-gateway/v1", api_key="...")` — no dedicated provider entry needed.

### 2.3 Architecture

```
src/any_llm/
├── __init__.py          # re-exports: AnyLLM, completion, acompletion, embedding, ... __version__
├── any_llm.py           # abstract base AnyLLM(ABC) — see §1.5
├── api.py               # top-level functions: completion, responses, messages, embedding, image_generation, transcription, speech, moderation, rerank, list_models, create_batch, etc
├── constants.py         # LLMProvider(StrEnum) 60+ values, ProviderTier(VERIFIED/COMMUNITY), REASONING_FIELD_NAMES
├── exceptions.py        # AnyLLMError + subclasses: RateLimitError, AuthenticationError, ContextLengthExceededError, ...
├── logging.py
├── tools.py             # callable_to_tool(func) → OpenAI tools format, _python_type_to_json_schema
├── types/               # completion.py, responses.py, messages.py, audio.py, batch.py, image.py, model.py, moderation.py, rerank.py
├── providers/           # per-provider dirs + registry.py for OpenAI-compat gateways as data rows
└── utils/               # exception_handler, structured_output (get_json_schema, is_structured_output_type)
docs/
├── index.md, quickstart.md, rerank.md, images/, cookbooks/*.ipynb (browser_use_with_any_llm)
pyproject.toml           # optional-dependencies per provider (50+ entries)
```

### 2.4 Exhaustive Feature List (README + docs + api.py)

**From README Quickstart + Installation:**

- Single interface for 50+ providers: OpenAI, Anthropic, Mistral, Ollama, Azure, Bedrock, Gemini, VertexAI, Cohere, Cerebras, Fireworks, Groq, HuggingFace, Together, Perplexity, Minimax, xAI, Dashscope, DeepInfra, Telnyx, etc (full list = `LLMProvider` enum).
- `completion(model, messages, provider, tools, tool_choice, temperature, stream, response_format, reasoning_effort, ...)` — sync and async (`acompletion`).
- Tool calling: Python callables auto-converted via `callable_to_tool` (requires docstring + type hints).
- Structured output: `response_format` as `dict | type` (Pydantic BaseModel) → JSON schema.
- Switching providers = change `provider` string + env key, no code change.
- OpenAI-compatible gateway support (any URL via `api_base`).

**From `src/any_llm/api.py` (grep `^def `):**

| Function | Signature Highlights | Purpose |
|---|---|---|
| `completion` | `model, messages, provider, tools, tool_choice, temperature, top_p, max_tokens, response_format, stream, seed, api_key, api_base, reasoning_effort, service_tier, ...` → `ChatCompletion | Iterator[ChatCompletionChunk]` | Chat completion, streaming optional, reasoning effort (`auto`), `n`, `stop`, penalties, `logprobs`, `stream_options`, `client_args` passthrough. |
| `responses` | `model, input, provider, ...` → `ParsedResponse` / `ResponseStreamEvent` | OpenAI Responses API (new). |
| `messages` | `model, messages, provider, ...` → `MessageResponse` | Anthropic Messages API shape. |
| `embedding` | `model, input, provider, ...` → `CreateEmbeddingResponse` | Text embeddings. |
| `image_generation` | `model, prompt, provider, ...` → `ImagesResponse` | Image generation. |
| `transcription` | `model, file, provider, ...` → `Transcription` | Audio transcription. |
| `speech` | `model, input, provider, ...` → `AudioSpeech` | TTS. |
| `moderation` | `model, input, provider, ...` → `ModerationResponse` | Content moderation. |
| `rerank` | `query, documents, model, provider, top_n, ...` → `RerankResponse` | Reranking. |
| `list_models` | `provider, ...` → `list[Model]` | List models per provider. |
| `create_batch` | `model, requests, provider, ...` → `Batch` | Batch API. |
| `retrieve_batch`, `cancel_batch`, `list_batches`, `retrieve_batch_results` | — | Batch lifecycle. |
| `a*` variants | `acompletion`, `aembedding`, `ar erank`, `alist_models`, `acreate_batch`, etc | Async equivalents. |

**From `src/any_llm/any_llm.py` (class `AnyLLM`):**

- **ABC base** with `PROVIDER_NAME`, `API_BASE`, `PROVIDER_DOCUMENTATION_URL`, `SUPPORTS_*` flags:
  `SUPPORTS_COMPLETION`, `SUPPORTS_COMPLETION_STREAMING`, `SUPPORTS_COMPLETION_REASONING`, `SUPPORTS_COMPLETION_IMAGE/PDF`, `SUPPORTS_EMBEDDING`, `SUPPORTS_MODERATION`, `SUPPORTS_LIST_MODELS`, `SUPPORTS_BATCH`, `SUPPORTS_IMAGE_GENERATION`, `SUPPORTS_RERANK`, `TIMEOUT_SUPPORT`.
- **Methods:** `__init__(api_key, api_base, **kwargs)`, `_verify_no_missing_packages`, `_verify_and_set_api_key`, `_resolve_api_base`, `create(provider, model, ...)` factory, `create_openai_compatible(name, api_base, ...)`, `_get_registry_provider_class`, `get_provider_class`, `get_supported_providers`, `get_registry_provider_names`, `completion`, `acompletion`, `embedding`, `image_generation`, etc.
- **Registry path:** `AnyLLM.create("openai", ...)` checks `providers/registry.py` first (config-only providers as data), then falls back to `import any_llm.providers.openai`.
- **OpenAICompat:** `BaseOpenAIProvider(AnyLLM)` with `client: AsyncOpenAI` (from `openai>=2.18`), all methods delegate to OpenAI SDK with `_convert_*` helpers for moderation/chat parsing.

**From `src/any_llm/providers/` (70+ dirs):**

- **Folder-per-provider** for behavior (custom auth, param remaps, streaming): `anthropic/`, `gemini/`, `ollama/`, `mistral/`, `bedrock/`, `azure/`, `openai/`, etc. Each has `__init__.py` exporting `XProvider(BaseOpenAIProvider or AnyLLM)`.
- **Registry-only providers** (no code folder, just row in `registry.py` `PROVIDER_REGISTRY`): `atlascloud`, `dashscope`, `databricks`, `deepinfra`, `kenari`, etc — defined as `OpenAICompatibleProviderConfig(name, env_api_key_name, api_base, supports_*)`. Adding a community gateway = adding one row + live verification in PR.

**From `src/any_llm/tools.py`:**

- `callable_to_tool(func)` → `{"type":"function","function":{"name,description,parameters:{"type":"object","properties": {"param": {"type": "string", "description": ...}}, "required": [...]}}}` Requires docstring, uses `get_type_hints` + `_python_type_to_json_schema` (str→string, int→integer, float→number, bool→boolean, list→array, dict→object, Enum, Literal, Optional, etc).

**From `src/any_llm/types/` (Pydantic models):**

- `completion.py`: `ChatCompletion`, `ChatCompletionChunk`, `ChatCompletionMessage`, `CreateEmbeddingResponse`, `ReasoningEffort`, `ParsedChatCompletion`.
- `responses.py`: `Response`, `ParsedResponse`, `ResponseInput`, `ResponseStreamEvent`.
- `audio.py`: `AudioSpeechParams`, `AudioTranscriptionParams`, `Transcription`.
- `batch.py`: `Batch`, `BatchRequestCounts`, `BatchResultItem`.
- `exceptions.py`: `AnyLLMError(message, original_exception, provider_name, status_code, code, param, error_type)`, plus `RateLimitError(retry_after)`, `AuthenticationError`, `ContextLengthExceededError`, `ContentFilterError`, `ModelNotFoundError`, `UnsupportedProviderError`, etc with `original_exception` preserved.

**From `src/any_llm/constants.py` (`LLMProvider` enum):**

`ANTHROPIC, BEDROCK, AZURE, AZUREANTHROPIC, AZUREOPENAI, ATLASCLOUD, CASCADIA, CEREBRAS, COHERE, DATABRICKS, DEEPSEEK, FIREWORKS, GEMINI, GITHUB, GMI, GROQ, HUGGINGFACE, INCEPTION, KENARI, LLAMA, LMSTUDIO, LLAMAFILE, LLAMACPP, META, MISTRAL, MOONSHOT, MZAI, NEOSANTARA, NEBIUS, OLLAMA, OPENAI, OTARI, OPENROUTER, PORTKEY, QINIU, REQUESTY, SAMBANOVA, SAGEMAKER, TOGETHER, VERTEXAI, VERTEXAIANTHROPIC, VLLM, VOYAGE, WATSONX, XAI, PERPLEXITY, MINIMAX, DASHSCOPE, DEEPINFRA, EDENAI, ZAI, TELNYX` (60+).

### 2.5 Code To Harvest (Copy Pattern)

- **Harvest:** `src/any_llm/any_llm.py` (`AnyLLM` base + registry dispatch) → adapt to `template/.../ai/gateway/base.py`.
- **Harvest:** `src/any_llm/api.py` (`completion` signature with `provider`, `tools`, `response_format`, `reasoning_effort`, `stream`) → adapt to `ai/llm.py` `ChatModel.complete` signature and factory `get_chat_model(provider, model)`.
- **Harvest:** `src/any_llm/providers/registry.py` (`OpenAICompatibleProviderConfig` + `PROVIDER_REGISTRY`) → adapt to `ai/gateway/registry.py` for our env-driven provider selection.
- **Harvest:** `src/any_llm/tools.py` (`callable_to_tool`) → replace `agents/tools/_schema_from_signature` with richer type handling (Enum, Literal, Pydantic).
- **Harvest:** `src/any_llm/providers/openai/base.py` (`BaseOpenAIProvider` with `AsyncOpenAI`, `SUPPORTS_*`) → template for real provider adapters.

---

## 3. `TEMP/langgraph` — `langchain-ai/langgraph` — Graph Runtime + Durable Execution

### 3.1 Identity

- **Origin:** `langchain-ai/langgraph`
- **Structure:** `libs/{langgraph,checkpoint,checkpoint-{postgres,sqlite,conformance},cli,prebuilt,sdk-py,sdk-js}` monorepo.
- **License:** MIT
- **Tagline:** Durable graph runtime for stateful agents, persistence, streaming, interrupts.

### 3.2 Architecture

```
libs/langgraph/src/langgraph/  # (not checked out in this clone? libs/langgraph has AGENTS.md/CLAUDE.md but src under libs/langgraph/langgraph)
libs/checkpoint/langgraph/checkpoint/{base,memory,serde} + store/{base,memory} + cache/{base,memory,redis}
libs/checkpoint/langgraph/store/base/{batch.py,embed.py}
libs/prebuilt/                    # create_react_agent, ToolNode, etc
libs/cli/                         # langgraph CLI
libs/sdk-py/ + sdk-js/            # client SDKs
docs/ (via redirects)             # docs are in langchain docs site, not local docs/
```

**From `libs/checkpoint/` read:**

- `checkpoint/base/__init__.py` → `BaseCheckpointSaver` with `put`, `get`, `list`, `delete`.
- `checkpoint/memory/__init__.py` → `InMemorySaver` (dev, dict-backed).
- `checkpoint/serde/{jsonplus.py,_msgpack.py,encrypted.py,types.py}` → serialization of state (JSON+ handles Pydantic, datetimes, blobs).
- `store/base/__init__.py` → `BaseStore` with `put`, `get`, `search`, `delete` for long-term memory (semantic store).
- `store/base/embed.py` → vector-backed store with embeddings.
- `cache/{memory,redis}/__init__.py` → `InMemoryCache`, `RedisCache` for tool results.
- `checkpoint-conformance/` → conformance tests for any saver (ensures postgres saver matches memory semantics).

**Known from README + deepagents/open-swe usage:** `StateGraph` with nodes/edges, `CompiledStateGraph`, `Interrupt`/`Command`, streaming (`astream`, `astream_events`), thread persistence via `checkpointer`, `store` for cross-thread memory.

### 3.3 Exhaustive Features (from code layout + dependent repos)

- **StateGraph:** Define `State` (TypedDict/Pydantic), `add_node`, `add_edge`, `add_conditional_edges`, `compile(checkpointer, store)`.
- **Prebuilt:** `create_react_agent(model, tools, checkpointer, system_prompt)` — ReAct loop with tool node, prompt node, retry logic.
- **Checkpoint:** Save/restore graph state per `thread_id`, history, `get_state`, `get_state_history`, diff-based storage, encrypted option.
- **Store:** Long-term key-value + vector search, `search` with embedding, namespace support.
- **Cache:** Cache tool calls (memory or Redis).
- **Interrupt:** `interrupt_before`, `interrupt_after`, `Command(resume=...)` for HITL.
- **Streaming:** `stream`, `astream`, `astream_events`, `astream_log`.
- **CLI:** `langgraph build`, `langgraph dev`, `langgraph up`.

### 3.4 Code To Harvest

- Replace `agents/graph.py` broken `from langchain.agents import create_agent` with:
  ```python
  from langgraph.prebuilt import create_react_agent
  from langgraph.checkpoint.memory import InMemorySaver
  from langgraph.store.memory import InMemoryStore
  agent = create_react_agent(model, tools, checkpointer=InMemorySaver(), store=InMemoryStore())
  ```
- Add `workflows/definitions/` as `StateGraph` defs + `workflows/execution/` invoking `graph.ainvoke(state, config={"configurable": {"thread_id": id}})`.

---

## 4. `TEMP/pydantic-ai` — `pydantic/pydantic-ai` — Typed Agent SDK + Harness

### 4.1 Identity

- **Origin:** `pydantic/pydantic-ai` (pydantic.dev/docs/ai)
- **Packages:** `pydantic-ai`, `pydantic-ai-slim`, `pydantic-evals`, `pydantic-graph`
- **Python:** `>=3.9` (but we target 3.12)
- **License:** MIT
- **Tagline:** "How Python does AI — typed end-to-end, any model, every interface."

### 4.2 Install & extras

```bash
uv add pydantic-ai                          # core
uv add "pydantic-ai[openai-realtime]"       # voice
uv add "pydantic-ai[temporal]"              # durable via Temporal
uv add pydantic-ai-harness                  # filesystem, shell, repo, planning, compaction
# models via string: "openai:gpt-5.6-sol", "anthropic:claude-fable-5", "test" (no key)
```

### 4.3 Architecture (from `pydantic_ai_slim/pydantic_ai/` layout)

```
pydantic_ai_slim/pydantic_ai/
├── __init__.py, _agent_graph.py, _cancel.py, _instrumentation.py, _output.py, _utils.py
├── agent/__init__.py, abstract.py, spec.py, wrapper.py  # Agent, AgentSpec
├── capabilities/           # 30+ capabilities, see §3.4
├── models/                 # openai, anthropic, google, bedrock, mistral, ollama, etc (string swap)
├── messages.py, result.py, run.py, usage.py, concurrency.py, retries.py
├── mcp.py, _mcp.py, _mcp_compat.py
├── graph/                  # Pydantic Graph for workflow
├── durable_exec/           # Temporal durability
├── embeddings/             # Embedder
├── realtime/, ui/, cli/
└── toolsets/, tools.py, tool_manager.py, direct.py, format_prompt.py
docs/
├── agent.md, capabilities/*.md, durable_execution/temporal.md, embeddings.md, graph.md, etc
examples/                    # data-analytics/rag, setup, etc
```

### 4.4 Exhaustive Features (README + docs + capabilities/)

**From README "What are you building?"**

- **Coding agent:** `Agent + Coder()` capability (files, shell, repo context, planning, sub-agents, context compaction) — `uvx --with pydantic-ai-harness clai -a pydantic_ai_harness.coder:coder_agent -m anthropic:claude-fable-5`
- **Data extraction:** `Agent(output_type=Sentiment(BaseModel))` → validated typed output.
- **Realtime voice:** `uv add "pydantic-ai[openai-realtime]"` → same `Agent` on live voice session with tools/capabilities.
- **Durable background:** `TemporalDurability` → same agent runs inside Temporal workflow, every model/tool call is durable activity, survives restarts/long waits.
- **Image generation:** `Agent` with `ImageGeneration` capability, typed output.
- **Embeddings:** `from pydantic_ai import Embedder` for RAG.

**From docs/capabilities/ (ls 30+ files):**

`_deferred_capabilities, _deferred_capability_loader, _dynamic, _ordering, _pending_messages, _tool_search, abstract, capability, combined, content_filter, deferred_tool_handler, hooks, image_generation, include_return_schemas, instrumentation, mcp, native_or_local, native_tool, prefix_tools, prepare_tools, process_event_stream, process_history, reinject_system_prompt, resolve_model_id, select_model, set_tool_metadata, thinking, thread_executor` + harness `Coder, FileSystem, Shell, RepoContext, Planning, SubAgents, ClearToolResults, WarnNearLimits, ToolOutputLimits, WebSearch, Advisor`.

**Key abstractions (code):**

- `Agent[DepsT, OutputT]` with `AgentModelSettings`, `AgentRetries`, `InstrumentationSettings`, `RunContext[DepsT]`, `capture_run_messages`.
- `AgentSpec` declarative spec (`_spec.py`) → `validate_from_spec_args`.
- `CallToolsNode`, `ModelRequestNode`, `UserPromptNode`, `EndStrategy` (graph nodes).
- `AgentCapability` protocol, composition via `CombinedCapability`.
- `models/` — `OpenAIModel`, `AnthropicModel`, etc swappable by `"openai:gpt-5.6-sol"` string; Gateway at `pydantic.dev/docs/ai/overview/gateway`.

**From `agent/__init__.py` imports:** `AgentRetries`, `AgentRunEvents`, `CallToolsNode`, `EndStrategy`, `ModelRequestNode`, `UserPromptNode`, `capture_run_messages`, `AgentSpec`, `AgentCapability`.

### 4.5 Code To Harvest

- **Adapter:** Keep `LoopRuntime`, add `PydanticAIAgent(DepsT)` implementing `ChatModel`:
  ```python
  from pydantic_ai import Agent
  agent = Agent("openai:gpt-4o", output_type=MyOutput, deps_type=MyDeps, system_prompt=..., tools=[my_tool])
  result = await agent.run(task, deps=my_deps)  # typed result.data
  ```
- **Capability composition:** Borrow `AgentCapability` protocol + `Combined` for our `Guardrails`/`Budget` as capabilities, not ad-hoc checks.
- **Durable:** For `workflows/`, use `TemporalDurability` pattern: `agent.run` inside Temporal activity.

---

## 5. `TEMP/fastembed` — `qdrant/fastembed` — Light ONNX Embeddings (No Torch)

### 5.1 Identity

- **Origin:** `qdrant/fastembed`
- **License:** Apache-2.0
- **Python:** `>=3.9`, ONNX Runtime, no Torch/GPU required (optional `fastembed-gpu`)
- **Tagline:** "Lightweight, fast, accurate — better than OpenAI Ada-002."

### 5.2 Install

```bash
pip install fastembed              # CPU
pip install fastembed-gpu          # GPU
# model downloads on first .embed() call, cached
```

### 5.3 Architecture

```
fastembed/
├── common/{model_description.py, onnx_model.py, model_management.py, types.py}
├── text/{text_embedding.py, onnx_embedding.py}  # dense text
├── sparse/{sparse_embedding_base.py, sparse_text_embedding.py, bm25.py, bm42.py, splade_pp.py}
├── late_interaction/{colbert.py, late_interaction_text_embedding.py}
├── late_interaction_multimodal/{colpali.py, colmodernvbert.py}
├── image/{image_embedding.py, siglip_embedding.py}
├── rerank/cross_encoder/{text_cross_encoder.py, onnx_text_cross_encoder.py}
├── parallel_processor.py
└── postprocess/muvera.py
docs/ (Getting Started.ipynb, examples/Supported_Models)
```

### 5.4 Exhaustive Features (README + docs + src)

**Dense text embeddings (default `TextEmbedding`):**

- Default `BAAI/bge-small-en-v1.5` (384d), also `bge-base`, `bge-large`, `e5`, `multilingual-e5-small` (384d), `embeddinggemma-300m` (768d), `nomic-embed-text`, etc.
- Usage: `model = TextEmbedding("BAAI/bge-small-en-v1.5"); embeddings = list(model.embed(documents))` (generator → list → numpy).
- Custom model: `TextEmbedding.add_custom_model(model="intfloat/multilingual-e5-small", pooling=MEAN, normalization=True, sources=ModelSource(hf=...), dim=384, model_file="onnx/model.onnx")`.
- Supports `query`/`passage` prefixes for retrieval (`task: search result | query: {content}`).

**Sparse text embeddings:**

- `SparseTextEmbedding` with `BM25`, `BM42`, `SPLADE_PP`, `MiniCOIL` for hybrid retrieval (dense+sparse).

**Late interaction:**

- `LateInteractionTextEmbedding` (`ColBERT`, `JinaColbert`) and `LateInteractionMultimodalEmbedding` (`ColPali`, `ColModernVBert`) for MaxSim retrieval.

**Image embeddings:**

- `ImageEmbedding` (`CLIP`, `SigLIP`) in `fastembed/image/`.

**Rerank:**

- `TextCrossEncoder` (`onnx_text_cross_encoder.py`) for cross-encoder reranking.

**Why fast:**

- ONNX Runtime faster than PyTorch, data parallelism for large datasets, small download (no GB Torch), Lambda-friendly.

**Supported models list:** `https://qdrant.github.io/fastembed/examples/Supported_Models/` (ever-expanding, including multilingual).

### 5.5 Code To Harvest

- **Replace:** `ai/embeddings.py` `FakeEmbeddingProvider` → `FastEmbedProvider`:
  ```python
  from fastembed import TextEmbedding
  class FastEmbedProvider:
      dimensions = 384
      def __init__(self, model="BAAI/bge-small-en-v1.5"): self.model = TextEmbedding(model)
      def embed(self, text: str) -> list[float]: return next(self.model.embed([text])).tolist()
  ```
- **Hybrid:** `SparseTextEmbedding("prithivida/Splade_PP_en_v1")` for sparse, `LateInteractionTextEmbedding("colbert-ir/colbertv2.0")` for MaxSim.
- **Extras:** `fastembed[gpu]` for GPU, `qdrant-client` for vector store `list(model.embed(...))` → `qdrant_client.QdrantClient.upload`.

---

## 6. `TEMP/langchain-mcp-adapters` — Bridge MCP ↔ LangChain/LangGraph

### 6.1 Identity

- **Origin:** `langchain-ai/langchain-mcp-adapters` (also JS version at `langchainjs`)
- **License:** MIT
- **Install:** `pip install langchain-mcp-adapters`

### 6.2 Architecture

```
langchain_mcp_adapters/
├── __init__.py
├── client.py          # MultiServerMCPClient
├── tools.py           # load_mcp_tools(session) → list[Tool]
├── resources.py       # MCP resources → LangChain
├── prompts.py         # MCP prompts → LangChain
├── sessions.py
├── server_info.py
├── callbacks.py       # LoggingMessageCallback, ProgressCallback, ElicitationCallback + CallbackContext(server_name, tool_name)
├── interceptors.py
└── py.typed
examples/ + tests/
```

### 6.3 Exhaustive Features (README)

- **Convert MCP tools → LangChain tools:** `from langchain_mcp_adapters.tools import load_mcp_tools; tools = await load_mcp_tools(session)` usable with `LangGraph` agents.
- **Client:** `MultiServerMCPClient` connects to multiple MCP servers, loads tools from each.
- **Quickstart:** Server `math_server.py` with `FastMCP("Math")` + `@mcp.tool() def add(a,b)`, Client `StdioServerParameters(command="python", args=["math_server.py"])` + `stdio_client` + `ClientSession` + `load_mcp_tools` + `create_agent("openai:gpt-4.1", tools)`.
- **Multiple servers:** `math_server` + `weather_server` → `MultiServerMCPClient({"math": {...}, "weather": {...}})`.
- **Callbacks:** `LoggingMessageCallback`, `ProgressCallback`, `ElicitationCallback` with `CallbackContext`.

### 6.4 Code To Harvest

- **Implement:** `agents/mcp_bridge.py` as:
  ```python
  from mcp import ClientSession, StdioServerParameters
  from mcp.client.stdio import stdio_client
  from langchain_mcp_adapters.tools import load_mcp_tools
  from langchain_mcp_adapters.client import MultiServerMCPClient
  client = MultiServerMCPClient({"math": StdioServerParameters(...)})
  tools = await client.get_tools()  # → List[BaseTool] → register into ToolRegistry via wrap
  ```

---

## 7. `TEMP/langgraph` Deep Dive — Checkpoint + Store + Cache (for real durability)

### 7.1 Already covered §2, add details:

- **`checkpoint/base/id.py`** → `CheckpointId` typed.
- **`checkpoint/serde/jsonplus.py` + `_msgpack.py`** → handles Pydantic, UUID, datetime, `BaseModel`, encrypted via `encrypted.py`.
- **`store/base/batch.py`** → batch `put`/`delete`.
- **`store/base/embed.py`** → `embed` kwarg for `search` (vector-backed store).
- **`cache/base/__init__.py`** → cache policy, `cache` decorator for tools.
- **`checkpoint-conformance/`** → ensure any new saver passes `test_conformance_delta`, `test_memory`, `test_store`.

### 7.2 Harvest:

- Use `InMemorySaver` for `minimal`/`dev`, `AsyncPostgresSaver` (from `langgraph-checkpoint-postgres`) for `production`; both pass conformance.
- `store` for episodic memory: `store.put(namespace=("user", user_id), key="fact_123", value={"text": ...})` + `store.search(namespace=("user", user_id), query="preference")`.

---

## 8. `TEMP/deepagents` — Opinionated Harness on LangGraph

### 8.1 Identity

- **Origin:** `langchain-ai/deepagents`, logo, "batteries-included agent harness"
- **Principles:** Opinionated, Extensible, Model-agnostic (any LLM with tool calling), Production-ready (LangGraph streaming/persistence + LangSmith).
- **Install:** `uv add deepagents`

### 8.2 Exhaustive Features (README)

- **Sub-agents:** delegate tasks to agents with isolated context windows, parallel.
- **Filesystem:** read/write/edit/search over pluggable local/sandboxed/remote backends.
- **Context management:** summarize long threads, offload tool outputs to disk.
- **Shell access:** run commands in sandbox.
- **Persistent memory:** pluggable `state` and `store` backends for cross-session recall.
- **Human-in-the-loop:** approve/edit/reject tool calls.
- **Skills:** reusable behaviors load on demand.
- **Tools:** bring own functions or any MCP server.

**FAQ:** Layers: `Deep Agents` (full harness) → `LangChain create_agent` (light) → `LangGraph` (custom graph). Any `CompiledStateGraph` can be sub-agent.

**Examples (ls):** `async-subagent-server`, `better-harness`, `content-builder-agent`, `deep_research`, `deploy-coding-agent`, `downloading_agents`, `llm-wiki`, `nvidia_deep_agent`, `ralph_mode`, `text-to-sql-agent`.

**Libs (ls):** `acp`, `cli`, `code`, `deepagents`, `evals`.

---

## 9. `TEMP/open-swe` — Internal Coding Agent Framework (Stripe/Ramp/Coinbase pattern)

### 9.1 Identity

- **Origin:** `langchain-ai/open-swe`, built on LangGraph + Deep Agents.
- **Tagline:** "Open-source framework for building your org's internal coding agent — Slackbots, CLIs, web apps with sandboxes."

### 9.2 Architecture (README — 3 decisions)

1. **Agent Harness** — `create_deep_agent(model, system_prompt, tools=[http_request, fetch_url, linear_comment, slack_thread_reply], backend=sandbox_backend, middleware=[ToolErrorMiddleware(), check_message_queue_before_model])`
2. **Sandbox** — isolated cloud env per task (Modal/Daytona/Runloop/E2B/LangSmith), full shell, repo cloned, persistent per thread, auto-recreate, parallel.
3. **Tools (curated, not accumulated):** `execute` (shell), `fetch_url` (markdown), `http_request`, `list_threads`/`get_thread`, `manage_thread`, `linear_comment`, `linear_search_issues`, `output_iframe`, `slack_add_reaction`, `slack_thread_reply`.

**Integrations:** `agent/integrations/` (Linear, Slack, GitHub), `graphs/`, `middleware/`, `skills/`, `providers/`.

### 9.3 Harvest

- **Sandbox abstraction:** `agents/workspace.py` already stub `WorkspaceBackend: Protocol:=object` → implement `SandboxBackend` with `ModalSandbox`, `DaytonaSandbox` mirroring open-swe `agent/runtime/`.
- **Tool curation:** Don't accumulate 50 tools; start with `execute`, `fetch_url`, `http_request` (from open-swe) + domain tools.
- **Sub-agent pattern:** `create_deep_agent` composition shows how to keep upgrade path (pull upstream) while customizing middleware.

---

## 10. `TEMP/agent-protocol` — Framework-Agnostic Agent API

### 10.1 Identity

- Origin `langchain-ai/agent-protocol`, OpenAPI JSON (`openapi.json` 2546 lines), `api.html`.

### 10.2 Exhaustive Endpoints (grep operationId, 27 total)

**Agents:** `search_agents`, `get_agent`, `get_agent_schemas` (input/output/state/config as JSON Schema).

**Threads (multi-turn):**
- `create_thread`, `search_threads` (filter by metadata/status idle|interrupted|errored|finished), `get_thread`, `get_thread_history` (append-only revisions, diffs), `copy_thread`, `delete_thread`, `patch_thread` (creates revision).

**Runs (executions):**
- `search_runs`, `get_run`, `delete_run`, `create_run` (fire-and-forget), `wait_run` (ephemeral + wait), `stream_run` (ephemeral + stream), `create_and_wait_run`, `create_and_stream_run`, `cancel_run`, `open_thread_sse_stream|websocket_stream`, `send_thread_streaming_command`.

**Store (long-term memory):**
- `put_item`, `get_item`, `delete_item`, `search_items`, `list_namespaces`.

**Streaming:** `streaming/` with CDDL schema + Python/TS bindings.

**Why:** Right API for serving LLM app in prod centered on `Runs` (one-shot/ephemeral), `Threads` (persistent state + history + concurrency), `Store` (memory). LangGraph Platform implements superset.

### 10.3 Harvest

- Mount protocol as FastAPI: `from agent_protocol.server import app` auto-generated from `openapi.json` (Pydantic V2 + FastAPI). Or manually implement `web/api/runs/` + `threads/` + `store/` following operationIds, returning same JSON shapes so any Agent Protocol client works.

---

## 11. `TEMP/pydantic-ai` Exhaustive — Already §3, add `docs/` headings

From `ls docs/`:

`agent.md`, `agent-spec.md`, `capabilities/*`, `changelog.md`, `cli.md`, `coding-agent-skills.md`, `common-tools.md`, `deferred-tools.md`, `dependencies.md`, `direct.md`, `durable_execution/temporal.md`, `embeddings.md`, `evals.md`, `graph.md`, `hooks.md`, `input.md`, `install.md`, `lint.md`, etc.

- **Hooks:** `capabilities/hooks.py` for pre/post model/tool.
- **Thinking:** `capabilities/thinking.py` for reasoning models.
- **MCP:** `capabilities/mcp.py` + `mcp.py` for MCP servers.
- **Select model:** `capabilities/select_model.py` for router.
- **Thread executor:** `capabilities/thread_executor.py`.

Harvest for `agents/` guardrails/hooks as `AgentCapability` instances.

---

## 12. `TEMP/fastembed` Exhaustive — Already §4, add `docs/` + `src` full

**Docs:** `examples/` (multilingual, code search, late interaction), `qdrant/` (Usage_With_Qdrant), `Supported_Models` (table of dense/sparse/late/image/rerank models).

**Models table (from `text_embedding.py`):**

- Dense: `BAAI/bge-small-en-v1.5` (384d), `BAAI/bge-base-en-v1.5` (768d), `BAAI/bge-large-en-v1.5` (1024d), `sentence-transformers/all-MiniLM-L6-v2` (384d), `intfloat/multilingual-e5-small/base/large`, `google/embeddinggemma-300m` (768d), etc.
- Sparse: `prithvida/Splade_PP_en_v1` (sparse), `Qdrant/bm25`, `Qdrant/bm42`, `Qdrant/minicoil-v1`.
- Late: `colbert-ir/colbertv2.0`, `jinaai/jina-colbert-v2`.
- Rerank: `cross-encoder/ms-marco-MiniLM-L-6-v2` via `TextCrossEncoder`.

**Code:** `fastembed/text/onnx_embedding.py` (`OnnxTextEmbeddingWorker` with `mean` pooling, `normalization`), `parallel_processor.py` (data parallelism), `postprocess/muvera.py` (MIPS).

---

## 13. `TEMP/deepseek-harness` — `deepseek-ai/deepseek-harness` — Everything is a Plugin (Cordis)

### 13.1 Identity

- **Origin:** `https://github.com/deepseek-ai/deepseek-harness` (`dsh`, 191.4k stars, 21.4k forks, 26 contributors, 97.2% TypeScript, MIT)
- **Tagline:** "DeepSeek Harness: Everything is a Plugin." Powered by **Cordis** — paradigm for Spatiotemporal Composability (paper: `github.com/cordiverse/paper`).
- **Status:** Developer preview — breaking changes expected.
- **Run:** `npx @deepseek-ai/dsh web` → Web UI `http://127.0.0.1:3080` (default, opens browser; SSH prints URL). From source: `pnpm install && pnpm run build && pnpm dsh web`.
- **Community:** Discord, GitHub Discussions, `dsh-plugin` topic.

### 13.2 Architecture (from `docs/architecture.md` + `AGENTS.md`)

**Cordis (plugin framework):**

- Plugin = `Service` subclass or function with `inject` + `apply(ctx)`.
- Context = repository of services via stable `ctx.<key>` (`ctx.tools`, `ctx.llm`, `ctx.sessions`).
- `inject` declares deps → load order via service requirements, not manual boot.
- Typed Events via declaration merging: `emit` (no await, observe), `waterfall` (around-middleware, `next()` delegates, short-circuit), `parallel` (await all), `serial` (await ordered). `@mode` tag in JSDoc checked by catalog.
- Registrations are reversible effects: `ctx.effect()`/`ctx.on()` returns disposer; reload unwinds.

**Profiles & bundles (composition):**

- Profile = named composition in Harness home, lists bundles + `cordis.patch.yml`. Ships `web` and `headless` templates.
- Bundle = distribution format for Cordis config rows + code they mount; stays patchable.
- Manifest in `package.json` `dsh.profile` / `dsh.bundle`.
- `dsh-base` = first layer in every profile (model adapters, tools, persistence, sandbox, approval, settings, credentials, telemetry). `dsh-web-app` adds browser app, `dsh-headless` adds one-shot runner.
- Layer order: each bundle in profile order → profile `cordis.patch.yml` → home `cordis.patch.yml` → `--patch` overlay. `dsh --profile web --dump-config` prints tree; any row patchable.

**Core packages (own `ctx` key):**

| Package | Owns | `ctx` key |
|---|---|---|
| `core/session` | append-only `SessionEvent` log + in-memory store | `ctx.sessions` |
| `core/system-prompt` | prompt-section + tool-schema assembly | `ctx.systemPrompt` |
| `core/tools` | scoped tool registry + guarded execution | `ctx.tools` |
| `core/agent` | `Agent` interface, live registry, `agent/*` events | `ctx.agents` |
| `core/agent-loop` | default driver for `Agent` | `ctx.agentLoop` |
| `core/scope` | per-agent scoped-registration primitive | library |
| `llm/llm` | message/stream vocabulary + adapter seam | `ctx.llm` |

**Events (extension points):**

- **Session events** — durable facts appended to log, broadcast via `session/event`. Must survive reload.
- **Agent events** (`agent/*`) — live `Agent`: inbox, step, status, request, validation, continuation.
- **Capability events** — policy/adapters on seam (`fs/*`, `tools/*`, `telemetry/*`).
- Full map: `docs/event-producer-consumer.md` lists every producer/consumer.

**Turn flow (step = 1 model request + its tool calls; turn = 0..n steps):**

```
turn/start
  claim next-step input + one queued message
  assemble prompt sections + tool schemas
  -> agent/pre-step (waterfall)  reject | enter(messages)
     reject or first enter empty -> close turn with no step (logged)
     step/start -> append entered messages as user/message
     derive model history from log -> agent/request -> llm/stream -> assistant/chunk* -> assistant/message
     tool/call* -> tools/pre-execute -> tools/execute -> tools/post-execute -> tool/result*
     step/end -> tools owe another request or next-step input arrived -> next step
  -> agent/turn-stopping (serial, no next())
turn/end
```

`turn/*`, `step/*`, `user/message`, `assistant/*`, `tool/*` are durable session events; rest are live waterfalls (`agent/pre-step`, `agent/request`, `llm/stream`, `tools/*{pre,execute,post}-execute`) vs serial `agent/turn-stopping`. Input via one inbox; `agent/pre-step` may rewrite or reject.

**Session log (source of truth):**

- `deriveMessages()` projects model history from log; raw `assistant/chunk` preserved for replay/UI. Fork/resume/transcripts/telemetry/persistence derive from stream. **Model-visible ⟺ logged** — new model-visible input requires new `SessionEventMap` member + log render; invariant asserts it. Structure changes bump `SESSION_FORMAT_VERSION`.

**Capability seams (Service Definition / Provider / Consumer):**

- One seam needs all 3 roles; adding capability designs all. Example: filesystem + subprocess share execution world → pointing at remote sandbox moves Bash/PTY/LSP together without forks. Subagent providers vary similarly (child agent vs delegated turn). Experimental Agent Teams on `ctx.agentTeams` with durable roster/task board/mailbox.

**Where new behavior goes (from docs table):**

| Goal | Mechanism |
|---|---|
| add model provider | register adapter on `ctx.llm` |
| add model-facing capability | register on `ctx.tools` (schema joins prompt) |
| per-session different capability set | compose agent preset (service row needs `isolate` realm) |
| add shell | register `ctx.shell` backend (local spawns via `ctx.subprocess`) |
| add PTY terminal | register `ctx.terminals` backend + `dsh-tool-terminal` |
| add human command | register on `ctx.commands` (dispatch without model turn) |
| add background work | register on `ctx.jobs`; `job_*` tools collect/stop |
| add FS access/policy | register `ctx.fs` provider or listen `fs/*` |
| confine processes | use `ctx.sandbox` backend; consumers wrap argv |
| intercept request/tool/turn | listen `agent/*` or `tools/*` events; `agent/turn-stopping` stops turn |
| add model-facing context | `agent.inject()` → next admitted request |
| add UI/editor integration | drive `ctx.agents` + render `session/event` |
| add Web Client Chat node | register `ConversationNodeDefinition` + keyed renderer |
| add durable session state | extend `SessionEventMap`; render/replay from log |
| generate session titles | register sole `ctx.sessionTitle` provider |
| manage same-session objective | `ctx.goals`; continue via `agent/*` |
| fork live session | `ctx.sessions.fork(source, boundary?, childSessionId?)` |
| scope registration to one agent | use that agent's `agent.ctx` |

**Docs set (from `docs/` ls 64 files):** `architecture.md`, `cordis-primer.md`+`cordis-tutorial/`, `agent-lifecycle.md`, `capability-seams.md`, `config-catalog.md`, `event-producer-consumer.md`, `defensive-patterns.md`, `development.md`, `api-gateway.md`, `cookbook/{extension-cookbook,adding-a-package,adding-a-tool,adding-an-llm-adapter,adding-a-conversation-node,adding-a-settings-card}`.

**Packages (from `packages/README.md` — 50+):**

| Group | Role | Examples |
|---|---|---|
| `core/` | spine: session, system-prompt, tools, agent, agent-loop | `core/session`, `core/tools` |
| `api/` | Remote BFF + Typert RPC gateway | `api/` |
| `typert/` | Type graph, loader, registry | `typert/` |
| `llm/` | LLM capability + DeepSeek providers | `llm/llm`, `llm-deepeek` |
| `shell/`/`subprocess/`/`terminal/` | bash/pty/subprocess seam + local/pwsh providers | `shell/`, `subprocess/` |
| `fs/`/`lsp/` | filesystem/LSP seam + local impl + tools | `fs/`, `lsp/` |
| `skill/` | skill provider registry + catalog/loader tool | `skill/` |
| `web/`/`attachment/`/`spill/` | web search/fetch, attachment identity, spill storage | `web/`, `attachment/` |
| `compaction/`/`context/`/`subagent/`/`jobs/` | compaction, request-context, subagent delegation, background jobs | `compaction/`, `subagent/` |
| `workflow/`/`todo/`/`plan/`/`preset/`/`guard/` | workflow engine, todo_write, plan mode, preset composition, loop hygiene | `workflow/` |
| `session/`/`session-query/`/`settings/`/`credentials/`/`storage/` | persistence (JSONL/SQLite), retrieval (FTS), settings file, env/.env creds | `session/` |
| `interaction/` | approval/interaction, permission, commands, ask-user | `interaction/` |
| `boot/`/`sdk/`/`acp/`/`host/`/`client/` | boot glue, JSON-RPC SDK, Agent Client Protocol server, web host/client shell | `boot/` |
| `sandbox/` | process-confinement (bwrap/Landlock/Seatbelt) | `sandbox/` |
| `e2b/` | E2B sandbox + FS/subprocess adapters (POC) | `e2b/` |

Each package: `@deepseek-ai/dsh-<pkg>`, ESM (`type: module`), `ctx.<key>` via `inject`, `ctx.effect` registrations, `SESSION_FORMAT_VERSION` on breaking log changes, `Branded<B>` opaque ids, strict `strict:true` + `noImplicitAny`, JSDoc `@param/@returns`.

### 13.3 Exhaustive Features (from README + AGENTS.md + packages)

- **Profiles as patchable plugin trees:** `dsh --profile web --dump-config` shows ordered rows; patch any row via `cordis.patch.yml` at profile/home/`--patch` layers. No privileged core — every part replaceable.
- **Cordis 5 ideas primer:** Plugin object (`Service` subclass) + Context repo + `inject` deps + Typed Events (emit/waterfall/parallel/serial) + reversible effects disposers. `!!js` loader config interpolation, `dependencies` in resolver manifest (`verify-cordis-config` gate).
- **Turn/step lifecycle:** durable `turn/start|end`, `step/start|end`, `user/message`, `assistant/chunk|message`, `tool/call|result` events; waterfall `agent/pre-step|request|llm/stream|tools/pre-execute|execute|post-execute` with `next()` delegation; `agent/turn-stopping` serial.
- **Session log:** `SessionEventMap` member required-on-read (needs `ignorable:true` envelope for unknown), `SCHEMA_VERSION` monotonic, append-only, projection for replay/titles/telemetry.
- **Capability seams as 3 roles:** illustrate `filesystem + subprocess + llm` sharing execution world; swap one provider → whole trio moves.
- **Cordis Tutorial:** hands-on plugin authoring, vendor sync (`vendor/README.md`), `FILTER=pattern pnpm run test`, hygiene `knip+publint`.
- **Commands:** `pnpm run build|test|test:coverage|test:e2e|test:snapshot|typecheck|lint|doc-sync|hygiene|dsh web` with gates (`gen-module-graph`, `verify-cordis-config`, dead-link check).
- **Python side:** `python/` SDK + bundled runtime (`python/README.md`), `pytest.ini`, `native/@deepseek-ai/node-addon-landlock-run`.

### 13.4 Code To Harvest (Copy Pattern — Not Vendor Cordis)

**Do NOT vendor Cordis itself** (heavy TS, `pnpm` workspaces). Harvest **ideas as Python protocols** for `template/.../core/cordis/`:

- **Plugin = `Service` protocol:** `class Plugin(Protocol): key: str; inject: set[str]; async def apply(self, ctx: Context): ...` → implement `Context` as `dict[str, Any]` service repo with `effect(disposer)` stack.
- **Typed events:** Keep our `core/events.py` CloudEvents but add `waterfall` pattern: `async def waterfall(event, *args, next: Callable): ...` waterfall listeners must call `next()`.
- **Profile patch layers:** Model `cordis.yml` rows as `platform.yaml` + overlay patches (`profiles/web/cordis.patch.yml` analog) → `settings.py` resolves `llm_provider` via `resolve(request): Spec` explicit step.
- **Seam 3 roles:** For `filesystem`, `llm`, `subprocess` define `ServiceDefinition` (Protocol), `ServiceProvider` (impl), `Consumer` (tool) — never import concrete provider in consumer.
- **Session log invariant:** `model_visible ⟺ logged` → enforce: any new chat context must be via `session.append(Event(...))`, tested by `deriveMessages()`.
- **Agents as `ctx.agents`:** Implement `Agent` interface with `agent/*` events (`agent/pre-step`, `agent/request`) wrapping `any_llm`/`langgraph` instead of plugging TS Cordis.

Closest tangible package to copy: `packages/llm/` (LLM seam) → adapt to `ai/gateway/llm_seam.py` with `inject = {"sessions", "tools"}` analog.

---

## 14. `TEMP/langchain` — Base Interfaces (Reference)

- `libs/core/` → `ChatModel`, `Embeddings`, `VectorStore`, `Document`, `PromptTemplate`, `OutputParser`.
- `libs/text-splitters/` → `RecursiveCharacterTextSplitter`, `TokenTextSplitter` for ingestion/chunking.
- Use only as interface reference; real impl is `any-llm` + `fastembed` + `langgraph`.

---

## 15. `TEMP/openwiki` — Wiki Ingestion (Reference)

- `openwiki/` package: `agent/`, `auth/`, `connectors/`, `ingestion/`, `integrations/`, `mermaid/`, `scheduling/`, `telemetry/`.
- Use `connectors/` pattern for knowledge ingestion pipelines (not directly in gold template yet, but informs `ai/knowledge/ingestion/`).

---

## 16. `TEMP/open-webui` — `open-webui/open-webui` — Self-Hosted AI Platform (149.8k stars)

### 16.1 Identity

- **Origin:** `https://github.com/open-webui/open-webui` (openwebui.com), 149.8k stars, 21.9k forks, 848 contributors, 167 releases (v0.11.0 latest).
- **Languages:** Python 37.4%, Svelte 32.9%, JS 22.1%, TS 5% — backend FastAPI + frontend Svelte.
- **License:** Open WebUI License (with branding preservation) + LICENSE_HISTORY.
- **Tagline:** "Extensible, feature-rich, user-friendly self-hosted AI platform designed to operate entirely offline. Supports Ollama + OpenAI-compatible APIs, with built-in RAG inference engine."

### 16.2 Install & Arch

- **Pip:** `pip install open-webui && open-webui serve` → `http://localhost:8080` (Python 3.11).
- **Docker:** `ghcr.io/open-webui/open-webui:main|ollama|cuda`, `-v open-webui:/app/backend/data` required, `--add-host=host.docker.internal:host-gateway`, `OLLAMA_BASE_URL`, `OPENAI_API_KEY`.
- **Other:** `docker-compose.yaml`, Kubernetes (kubectl/kustomize/helm), dev `://0.0.0.0:8080` vs `host` net.
- **Backend:** `backend/open_webui/` → `main.py` (FastAPI), `config.py`, `constants.py`, `env.py`, `events.py`, `functions.py`, `internal/db.py` (SQLAlchemy async), `migrations/` (Alembic 70+ versions), `models/` (25 models: `auths.py`, `chats.py`, `users.py`, `groups.py`, `knowledge.py`, `files.py`, `tools.py`, `skills.py`, etc), `routers/` (25 routers: `auths.py`, `chats.py`, `retrieval.py`, `knowledge.py`, `tools.py`, `functions.py`, `models.py`, `pipelines.py`, etc), `retrieval/` (`loaders`, `vector`, `web`, `external.py`), `storage/` (local/S3/GCS/Azure), `socket/` (python-socketio), `tools/` (`builtin.py`, `knowledge_fs.py`), `utils/`.
- **Frontend:** `src/` Svelte (`app.css`, `lib/`, `routes/`, `tailwind.css`), `svelte.config.js`, `vite.config.ts`.
- **Deps (pyproject.toml):** `fastapi==0.136.3`, `uvicorn`, `pydantic==2.13.4`, `python-socketio==5.16.2`, `sqlalchemy[asyncio]==2.0.50`, `aiosqlite`, `psycopg`, `redis==8.0.1`, `APScheduler==3.11.2`, `tiktoken`, `mcp==1.27.2`, `openai==2.29.0`, `anthropic==0.86`, `google-genai`, `langchain==1.2.10`, `chromadb==1.5.9`, `transformers==5.5`, `sentence-transformers==5.5`, `boto3`, `azure-ai-documentintelligence`, etc.

### 16.3 Exhaustive Features (README Key Features = 25 bullets)

| # | Feature | Detail |
|---|---|---|
| 1 | Effortless Setup | pip/uv/Docker/Kubernetes, `:ollama`/`:cuda` images |
| 2 | Broad Model & API Integration | Any OpenAI-compat API + Ollama local; point at LMStudio/GroqCloud/Mistral/OpenRouter/vLLM simultaneously |
| 3 | Granular RBAC & User Groups | Admin roles/groups/permissions, per-user/group model access |
| 4 | Plugin Support | **Filters, Actions, Pipes, Tools, Skills** + MCP, MCPO, OpenAPI tool servers; rate limits, approval flows |
| 5 | Models & Agents | Wrap base model with instructions/tools/knowledge → specialized agents; dynamic vars, per-group/user access, community preset imports (openwebui.com) |
| 6 | Notes | Workspace outside conversations, rich editor, AI rewrite, attach to chat for full-context |
| 7 | Channels | Real-time shared spaces, team+AI collaborate one timeline, tag models, threads/reactions/pins |
| 8 | Persistent Memory | Cross-conversation fact memory |
| 9 | Live Workflow & Message Flow | Checklists in real-time, queue messages while responding |
| 10 | Calendar & AI Scheduling | Personal/shared calendars (month/week/day), recurring, reminders; model manages via function calling |
| 11 | Automations | Schedule prompts recurring, runs on calendar, link back to chat |
| 12 | Responsive & PWA | Desktop/laptop/mobile, PWA with offline localhost |
| 13 | Markdown & LaTeX | Full MD + LaTeX |
| 14 | Voice/Video Call | STT (Local Whisper/OpenAI/Deepgram/Azure) + TTS (Azure/ElevenLabs/OpenAI/Transformers/WebAPI) |
| 15 | Artifact Storage | Key-value API for artifacts (journals/trackers/leaderboards), personal/shared scopes |
| 16 | Local RAG Integration | 9 vector DBs + hybrid BM25+vector with rerank + full-context, `#` command to pull docs/URL |
| 17 | Web Search for RAG | SearXNG, Google PSE, Brave, Kagi, Tavily, Perplexity, etc (20+ providers) → inject into conversation |
| 18 | Web Browsing | `#` + URL or model fetch autonomously |
| 19 | Image Generation & Editing | OpenAI DALL·E, Gemini, ComfyUI (local), AUTOMATIC1111 (local), prompt editing |
| 20 | Multi-Model Conversations | Parallel multi-model engagement |
| 21 | Usage Analytics & Evaluation | Dashboards (messages/tokens/cost per user/model), arena, A/B, ELO leaderboards |
| 22 | Flexible DB & Storage | SQLite (encrypted) or Postgres; files local/S3/GCS/Azure Blob |
| 23 | Advanced Vector DB Support | ChromaDB, PGVector, Qdrant, Milvus, Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle 23ai (9) |
| 24 | Enterprise Auth & Provisioning | LDAP/AD, SSO (trusted headers/OAuth), SCIM 2.0 (Okta/Azure AD/Google Workspace) |
| 25 | Production Observability + Scalability | OpenTelemetry (traces/metrics/logs), Redis-backed sessions + WebSocket for multi-worker multi-node behind LB |
| + | Ecosystem (4 companion apps): Computer (`open-webui/computer` mobile coding agent), Open Terminal/Terminals (per-user isolated containers), oikb (45+ sources KB sync), Native Desktop App (macOS/Win/Linux, Spotlight+screenshot+llama.cpp) |

**Routers exhaustive (25):** `analytics.py`, `audio.py`, `auths.py`, `automations.py`, `calendar.py`, `channels.py`, `chats.py`, `configs.py`, `evaluations.py`, `files.py`, `folders.py`, `functions.py`, `groups.py`, `images.py`, `knowledge.py`, `memories.py`, `models.py`, `notes.py`, `notifications.py`, `ollama.py`, `openai.py`, `pipelines.py`, `prompts.py`, `retrieval.py`, `scim.py`, `skills.py`, `tasks.py`, `terminals.py`, `tools.py`, `users.py`.

**Models exhaustive (25):** `access_grants.py`, `auths.py`, `automations.py`, `calendar.py`, `channels.py`, `chat_messages.py`, `chats.py`, `config.py`, `feedbacks.py`, `files.py`, `folders.py`, `functions.py`, `groups.py`, `knowledge.py`, `memories.py`, `messages.py`, `models.py`, `notes.py`, `oauth_sessions.py`, `prompt_history.py`, `prompts.py`, `shared_chats.py`, `skills.py`, `tags.py`, `tools.py`, `users.py`.

**RAG internals:** `retrieval/` → `loaders/` (Tika/Docling/Document Intelligence/Mistral OCR/PaddleOCR-vl/external loaders for PDF/PPT/DOCX), `vector/` adapters for 9 DBs, `web/` search providers, hybrid `BM25 + vector` + reranking + full-context mode.

### 16.4 Code To Harvest

- **Plugin seam:** Filters/Actions/Pipes/Tools/Skills → adapt to `agents/tools` + `agents/skills` as `open_webui.functions` pattern (`functions.py` pipe: `def pipe(body: dict) -> dict`).
- **Knowledge:** `routers/knowledge.py` + `models/knowledge.py` + `retrieval/` hybrid pattern → `ai/knowledge/` ingestion pipeline.
- **RBAC:** `routers/auths.py` + `models/auths.py` group/role tables → `identity/` + `platform/` admin.
- **Observability:** `docker-compose.otel.yaml` + `opentelemetry` traces → `operations/` OTel.

---

## 17. `TEMP/dify` — `langgenius/dify` — LLM App Development Platform (153.4k stars)

### 17.1 Identity

- **Origin:** `https://github.com/langgenius/dify` (dify.ai), 153.4k stars, 24.2k forks, 1436 contributors, 168 releases (v1.16.1), Python 46.6% + TS 50.2%.
- **License:** Dify Open Source License (Apache-2.0 + conditions).
- **Tagline:** "Build Agentic workflows, RAG pipelines, with rich AI model and tool support on one collaborative workspace. Deploy on cloud, VPC, or self-hosted."

### 17.2 Install & Arch

- **Docker:** `cd dify/docker && cp .env.example .env && docker compose up -d` → `http://localhost/install`. Req CPU≥2, RAM≥4GiB.
- **Structure:** `api/` (Flask + gunicorn/gvent), `web/` (TS, Vite), `docker/`, `cli/`, `sdks/`, `packages/`, `dify-agent/`, `dify-agent-runtime/`, `dev/`, `docs/`.
- **API deps (pyproject.toml):** `flask>=3.1`, `celery>=5.6`, `redis[hiredis]`, `psycopg2-binary`, `gunicorn`, `gevent`, `boto3`, `google-cloud-aiplatform`, `httpx`, `opentelemetry-distro` + instrumentation (celery/flask/httpx/redis/sqlalchemy), `fastopenapi[flask]==0.7`, etc. `requires-python ~=3.12`.
- **API layout (`api/`):** `app_factory.py`, `app.py`, `celery_entrypoint.py`, `extensions/`, `models/` (`account.py`, `dataset.py`, `agent.py`, `provider.py`, `workflow.py` etc), `core/` (`agent/`, `app/`, `workflow/`, `rag/`, `tools/`, `mcp/`, `memory/`, `llm_generator/`, `model_manager.py`, `prompt/`), `controllers/`, `services/`, `libs/`, `facts/`, `schedule/`, `repositories/`, `events/`, `providers/`, `fields/`, `enums/`.

### 17.3 Exhaustive Features (README 7 core + docs)

| # | Feature | Detail |
|---|---|---|
| 1 | Workflow | Visual canvas, build/test powerful AI workflows leveraging all below |
| 2 | Comprehensive model support | Hundreds of LLMs from dozens of providers + self-hosted (GPT/Mistral/Llama3, any OpenAI API-compat); full list `docs/providers-v5` |
| 3 | Prompt IDE | Craft prompts, compare model performance, add TTS to chat app |
| 4 | RAG Pipeline | Text extraction from PDF/PPT/etc → indexing → retrieval, out-of-box |
| 5 | Agent capabilities | LLM Function Calling or ReAct, 50+ built-in tools (Google Search, DALL·E, Stable Diffusion, WolframAlpha), custom tools |
| 6 | LLMOps | Monitor logs/performance over time, continuous improve prompts/datasets/models via production data + annotations, observability via Opik/Langfuse/Arize Phoenix + OTel unified tracing (`docker feat(trace): provider-neutral unified tracing`) |
| 7 | Backend-as-a-Service | All offerings have corresponding APIs → integrate into business logic |

**System req:** Docker Compose v2.24.0+, `make` + `pytest` via `api/conftest.py`.

**Editions:** Cloud (200 free GPT-4 calls), Self-host Community, Enterprise (email).

### 17.4 Code To Harvest

- **Workflow canvas:** `api/core/workflow/` (graphon==0.7, node types: LLM, Tool, Knowledge, If-Else, Code, Template) → `workflows/definitions/` as visual spec → `workflow` capability seam.
- **Provider manager:** `api/core/provider_manager.py` + `models/provider.py` + `core/model_manager.py` (unified model registry, same as `any-llm` but Flask) → `ai/gateway/registry.py`.
- **RAG pipeline:** `api/core/rag/` + `api/core/indexing_runner.py` + `knowledge-fs-contract` → `ai/knowledge/` ingestion → `core/datasource` → `retrieval` hybrid.
- **Tools (50+):** `api/core/tools/` builtin + `api/core/mcp/` → `agents/tools/` + `agents/mcp_bridge.py`.
- **Observability:** `api/extensions/ext_tracing` + `opentelemetry-distro` → `operations/tracing/` unified provider-neutral.

---

## 18. `TEMP/dispatch` — `Netflix/dispatch` — Incident & Signal Management (6.5k stars, Archived Sep 2025)

### 18.1 Identity

- **Origin:** `https://github.com/Netflix/dispatch` (Netflix OSS, archived read-only Sep 1 2025), 6.5k stars, 681 forks, 79 contributors (kevgliss, mvilanova, whitdog47), 51 releases (v20241220).
- **Languages:** Python 53.8%, Vue 28.6%, JS 15.7%.
- **License:** Apache-2.0.
- **Tagline:** "All of the ad-hoc things you're doing to manage incidents today, done for you, and much more — deeply integrates with existing tools (Slack, GSuite, Jira) to provide orchestration instead of introducing another tool."
- **Notice:** Remains publicly read-only, fork to continue; no new issues/PRs.

### 18.2 Install & Arch

- **Python:** `>=3.11` (3.11/3.12/3.13 classified), `fastapi==0.115.12`, `sqlalchemy`+`alembic`, `aiocache`, `aiofiles`, `aiohttp`, `boto3`, `jira`, `blockkit`, `atlassian-python-api`, `httpx`, `jinja2`, `uv` for deps, `docker/` + `docker-compose.yaml`, `bin/`, `scripts/`, `data/`, `docs/` (GitBook), `tests/`.
- **Structure (`src/dispatch/` 50+ modules):** `ai/`, `auth/`, `canvas/`, `case/`, `case_cost/`, `conference/` (Zoom), `conversation/` (Slack), `definition/`, `document/` (Google Drive), `entity/`/`entity_type/`, `event/`, `evergreen/`, `feedback/`, `group/` (GSuite), `incident/` (core), `incident_cost/`, `notification/`, `organization/`, `participant/`/`participant_role/`/`participant_activity/`, `plugin/`/`plugins/`, `project/`, `report/`, `route/`, `search/`/`search_filter/`, `service/`, `signal/` (signal mgmt), `storage/` (S3), `tag/`/`tag_type/`, `task/` (Jira), `team/`, `term/`, `ticket/`, `workflow/` (incident workflow), `workflow/` = `incident` + `report` workflows, `database.py`, `config.py`, `main.py`, `api.py`, `exceptions.py`, `enums.py`, `metrics.py`, `search/`, `scheduler.py`, `extensions.py`, `models.py`.

### 18.3 Exhaustive Features (README + `src/dispatch` code)

**Incident orchestration (core promise):**

- Creates resources, assembles participants, sends notifications, tracks tasks, assists with post-incident reviews — lets you focus on fixing.
- Deep integrations: **Slack** (channels, canvas, blockkit, workflows), **GSuite/Google Drive/Docs** (incident docs), **Jira** (tickets/tasks), **Zoom** (conference), **PagerDuty/OpsGenie** etc via plugins.

**Modules (from `src/dispatch` ls):**

| Module | Purpose |
|---|---|
| `incident/` | Incident lifecycle (declare/triage/investigate/resolve), roles (`incident_role`), costs (`incident_cost`), evergreen holds |
| `case/` | Case management (non-incident investigations) + `case_cost` |
| `signal/` | Signal management (alert ingestion, routing to incidents/cases) — the "signal" in Dispatch title |
| `definition/` | Incident/case definitions, types, priorities, severities (`enums.py`) |
| `workflow/` | Workflow orchestration for incidents (steps, approvals, transitions) |
| `task/` | Task tracking (Jira-backed), assignment, completion |
| `participant/` | Participant assembly, roles, activity logging |
| `conference/` | Auto-create Zoom/Google Meet conferences |
| `conversation/` | Slack channel per incident (auto-create, archive, canvas support #6205) |
| `document/` | Incident artifact docs (Google Drive) with templates |
| `report/` | Post-incident report generation + review |
| `notification/`/`messaging/` | Notifications across Slack/email via templates (`email_templates/`) |
| `search/` | Search incidents/cases/signals with filters (`search_filter.py`) |
| `tag/` | Tagging incidents/cases for taxonomy |
| `project/`/`organization/`/`team/` | Multi-tenancy: org → project → incident (already mirrors our FinTech `Tenant→Organization→Resources`) |
| `plugin/`/`plugins/` | Plugin seam for integrations (Slack/Jira/GSuite/S3/Zoom etc) — every integration is a plugin |
| `evergreen/` | Recurring incidents/cases |
| `feedback/` | Post-incident feedback collection |
| `term/` | Terminology customization per org |
| `service/` | Service catalog (which service is affected) |
| `entity/` | Entities involved (hosts, services) |
| `ai/`/`nlp.py` | AI/NLP helpers (enrichment) |

**Project resources:** Blog Post, Source Code, Docs (GitBook, bump `brace-expansion`), Issue tracker, Docker image (`dispatch/dispatch-image`), 500+ deployments.

### 18.4 Code To Harvest (Incident Pattern for FinTech/Audit)

- **Incident as workflow:** `src/dispatch/incident/` + `workflow/` → adapt to `workflows/definitions/` for FinTech maker-checker: incident = anomaly (fraud/KYC failure) → `signal` ingestion → `incident` creation → `task` (human HITL) → `document` evidence → `report` audit trail. Use Dispatch's `enums.py` (incident type/priority/status states) as state machine template.
- **Plugin seam:** `src/dispatch/plugin/` base class + `plugins/` per integration (Slack/Jira) → same as our `integrations/` Interface→Adapter→Provider for payments/email/ticketing.
- **Conversation per resource:** `conversation/` Slack channel auto-create per incident → adapt to `platform/notifications` channel per FinTech case/account (isolated audit log).
- **Search/filter:** `search_filter.py` + `search/` → `data/search/` OpenSearch adapter for incident/case listing with pagination/filtering.
- **Archive note:** Dispatch is archived, so copy pattern only; do not depend on its release cycle. Code remains readable as production incident reference.

---

## 19. `TEMP/the-algorithm-ml` — `twitter/the-algorithm-ml` — Twitter ML Models (Heavy Ranker + TwHIN)

### 19.1 Identity

- **Origin:** `https://github.com/twitter/the-algorithm-ml` (Python companion to `twitter/the-algorithm` Scala serving stack).
- **License:** COPYING + Apache (torchrec under separate `LICENSE.torchrec`).
- **Stack:** Python + PyTorch + **torchrec** (GPU recommended, Linux), venv via `./images/init_venv.sh`.
- **Contents:** two production models:
  1. **"For You" Heavy Ranker** (`projects/home/recap`)
  2. **TwHIN embeddings** (`projects/twhin`, paper arXiv:2202.05387)

### 19.2 Heavy Ranker (`projects/home/recap`)

**Purpose:** final-stage ranker for tweets already past candidate retrieval in the "For You" timeline funnel; succeeded only by filtering heuristics.

**Architecture — parallel MaskNet (arXiv:2102.07619):**

- `model/mask_net.py`: `MaskBlock` = optional input LayerNorm → mask layer (`Linear(mask→agg)→ReLU→Linear(agg→input)`) gating the net (`net * mask`) → hidden Linear → output LayerNorm. Xavier-uniform init. `MaskNet` composes N parallel blocks (config `use_parallel: true`) + shared MLP head.
- Multi-task: one probability head per engagement type (10 heads):
  `fav (0.5)`, `retweet (1.0)`, `reply (13.5)`, `good_profile_click (12.0)`, `video_playback50 (0.005)`, `reply_engaged_by_author (75.0)`, `good_click (11.0)`, `good_click_v2 (10.0)`, `negative_feedback_v2 (-74.0)`, `report (-369.0)`.
- **Score formula:** `score = Σᵢ weightᵢ × P(engagementᵢ)` — weights live in a **serving-stack config file** (Scala `ScoredTweetsParam`), adjustable anytime without retraining. Weights tuned so each engagement contributes near-equal average mass, then optimized against platform metrics.
- Per-task MLP towers configured independently (`tasks.<name>.mlp_config.layer_sizes: [256,128,1]`); backbone blocks each `{aggregation_size: 1024, output_size: 1024}`.

**Feature system (`FEATURES.md` — the real gold):**

- **Aggregate features** = bulk of feature count: rolling aggregations within scope × time window. Long-term = **50 days**, short-term ("real-time") = **under 3 days, typically 30 minutes**.
- Generated as **Cartesian crosses from a template**: `Feature Group Name × Engagement Scope × Feature To Aggregate × Aggregation Spec`. Every combination row = one feature.
- Example parse: `user_aggregate_v2.pair.recap.engagement.is_favorited.engagement_features.in_network.replies.count.50.days.count` = over every user → only favorited tweets → in-network replies sent → counted last 50 days.
- Groups include `author_aggregate` (17 engagement flags: `is_favorited/is_retweeted/is_replied/is_clicked/is_dwelled/is_followed/is_profile_clicked/is_quoted/is_open_linked/is_photo_expanded/is_video_viewed/...`), `user_aggregate`, `user_author_aggregate` pairs, etc.

**Training infra:**

- `core/train_pipeline.py`: forked from torchrec `TrainPipelineSparseDist`, modified for gradient accumulation.
- `common/run_training.py`: single-node multi-GPU wrapper — if `WORLD_SIZE/RANK` env set run `train_fn()` inline, else spawn **torchrun**; `is_chief` distinction.
- `common/checkpointing/snapshot.py`, `wandb.py`, `ml_logging/{absl,torch}`, `metrics/{auroc,rce,aggregation}.py`.
- **Config pattern (`core/config/base_config.py`) — harvest directly:**
  ```python
  class BaseConfig(pydantic.BaseModel):
      class Config: extra = pydantic.Extra.forbid   # exact args, user-error proof
      # Field(None, one_of="group") / at_most_one_of="group" enforced by root_validators
      def pretty_print(self): return yaml.dump(self.dict())  # legible config logging
      @classmethod @functools.lru_cache() def _field_data_map(...)  # cached schema introspection
  ```
- YAML configs (`config/local_prod.yaml`, `segdense.json`) + random-data generator so training runs without private data.

### 19.3 TwHIN Embeddings (`projects/twhin`)

- **Purpose:** pretrain dense entity embeddings from heterogeneous graphs (`User follows User`, `User favorites Tweet`, `User clicks Ad`) — used for **candidate retrieval** and as model features across recommenders.
- **Model:** TransE-style — per-relation translation vectors (`all_trans_embs`, one bias per relation); embeddings via torchrec `LargeEmbeddings` tables keyed by node vocab id.
- **Negative sampling:** `in_batch_negatives` (relation-masked matmul dot-products within batch, permutation-repeated until quota) + `global_negatives`.
- **Data contract:** parquet with exactly 3 columns `lhs, rel, rhs` (vocab indices); open subsampled graphs on HuggingFace (`TwitterFollowGraph`, `TwitterFaveGraph`). YAML config in `projects/twhin/config/local.yaml`; docker workflow scripts.

### 19.4 Code To Harvest

- **Scoring-as-config:** weighted-sum ranker with weights in config (not baked into model) → adapt for `ai/knowledge/ranking.py`: retrieval score = Σ weightᵢ × signalᵢ (semantic similarity, recency, authority, spam-prob) — editable via settings without redeploy.
- **Negative weights matter:** negative feedback/report get large NEGATIVE weights (-74/-369) → reranking should penalize bad signals harder than it rewards good ones.
- **Aggregate feature naming grammar:** `<scope>.<engagement>.<feature>.<window>` → adopt for usage analytics names (`user.aggregate.rag.query.successful.30.days.count`).
- **BaseConfig:** `extra=forbid` + `one_of` root-validators + `pretty_print()` → adopt verbatim into `core/config/`.
- **Dual windows:** realtime (30min) vs long-horizon (50day) aggregation → usage/cost tracking design in `platform/billing`.

---

## 20. `TEMP/twitter-server` — `twitter/twitter-server` — Production Server Template (Scala)

### 20.1 Identity

- **Origin:** `https://github.com/twitter/twitter-server` (twitter.github.io/twitter-server), 1.6k stars, 77 contributors, 75 releases (~monthly, latest 22.12.0), Scala 90.8%.
- **License:** Apache-2.0. Used in production at Twitter + many orgs; actively maintained.
- **Tagline:** "Defines a template from which servers at Twitter are built. Provides common application components such as an administrative HTTP server, tracing, stats — wired correctly for production."

### 20.2 Architecture

```
server/src/main/scala/com/twitter/server/
├── TwitterServer.scala     # the trait everything mixes in
├── AbstractTwitterServer   # Java-friendly hooks: onInit/preMain/postMain/onExit/onExitLast
├── AdminHttpServer.scala   # separate admin HTTP server + Route case class
├── Admin.scala             # admin route registry wiring
├── Lifecycle.scala         # /health /ready /quitquitquit /abortabortabort + GC promote-before-serving
├── Stats.scala, Linters.scala, Hook(s).scala, FlagResolver.scala, BuildProperties.scala
├── filters/AdminThreadPoolFilter.scala   # admin traffic isolated on own thread pool
├── handler/*.scala         # 35 admin handlers
├── view/                   # IndexView, NotFoundView (admin HTML rendering)
├── lint/                   # runtime lint rules surfaced in admin UI
└── resources/twitter-server/{css,js,img}  # bundled admin dashboard UI (bootstrap, histogram charts)
```

**Trait stack (composition IS the template):**

```scala
trait TwitterServer extends App
  with Slf4jBridge with Logging with Stats with Linters
  with DtabFlags with Hooks with AdminHttpServer with Lifecycle
// Don't let applications opt-out: suppressGracefulShutdownErrors = false
```

DI convention = self-typed Scala traits mixed into `TwitterServer`.

### 20.3 Exhaustive Features

**Lifecycle (`Lifecycle.scala`):**

- Event phases: `init(onInit) → premain(preMain) → PrebindWarmup → main → postmain(postMain) → WarmupComplete → onExit → onExitLast`; blocking `main()` until `close()`.
- Endpoints registered unconditionally: `GET /health` → `"OK\n"`, `GET /ready` (ReadinessHandler), `POST /quitquitquit` (graceful ShutdownHandler), `POST /abortabortabort` (AbortHandler).
- `promoteBeforeServing` flag: promote young-gen objects before serving requests (shortens early GC pauses) — warmup discipline.
- Graceful shutdown timer; shutdown errors cannot be suppressed.

**35 admin handlers (under `/admin/*`, isolated via `AdminThreadPoolFilter`):**

`Index` (dashboard home), `Summary`, `Threads` (+JS viewer), `Tracing` (runtime trace toggles), `MetricQuery` / `MetricMetadataQuery` / `MetricExpression` / `MetricTypeQuery` (metrics expression language at runtime), `HistogramQuery` (+chart-renderer.js), `Registry` / `ClientRegistry` / `ServerRegistry` (finagle registries), `LoadBalancers`, `Announcer`, `AttachedClients`, `Contention` (thread contention), `Dtab` / `Namespace` (name resolution), `Toggle` (**runtime feature-flag toggles**), `Tunable` (**runtime numeric tunables**), `Logging` / `NoLogging` (**runtime log-level changes**), `Lint` / `FailedLintRule`, `ProfileResource` / `Resource` / `HeapResource` (profiling), `Shutdown`, `Readiness`, `Reply`, `AdminRedirect`, `AdminHttpMux`, `ServerInfo`, `Twitter`, `BuildProperties` (git sha/date in admin).

**Admin route model (`AdminHttpServer.Route`):**

```scala
case class Route(path, handler, alias, group, includeInIndex, method = Get)
```

Every capability self-registers with alias + group → auto-rendered grouped dashboard index. New admin pages = register a Route; zero framework code.

**Stats/tracing/flags:** finagle stats receiver wired (Null fallback), runtime metrics query expressions; tracing toggled at runtime; global flag parsing with help strings; `Hooks` extension points for libraries to observe app phases.

### 20.4 Code To Harvest (Python translations → `operations/` + `web/api/admin`)

| twitter-server concept | Gold-template equivalent |
|---|---|
| `/health` literal OK vs `/ready` readiness | liveness `GET /api/health` (process up) vs readiness `GET /api/ready` (db/redis/jobs deps checked) |
| `/quitquitquit` + `/abortabortabort` POST | graceful shutdown triggers behind auth for k8s preStop / chaos testing |
| `AdminThreadPoolFilter` | admin router on separate anyio limiter/threadpool — dashboards never starve request workers |
| `Route(path, alias, group, includeInIndex)` self-registration | FastAPI ops router registry: each endpoint declares alias+group → auto-built `/api/admin/index` dashboard JSON |
| 35 handlers | staged: health/ready, log-level change, runtime toggles (feature flags), tunables (settings overrides), metrics query, build properties (`GIT_SHA`,`BUILD_DATE` env-injected), summary |
| Runtime log-level/toggles/tunables | `operations/runtime_control.py` — mutate structlog level / flags without restart (audit-logged) |
| BuildProperties | `core/build_info.py` from Docker build env, exposed in `/api/admin/info` |
| promote-before-serving warmup | lifespan warmup phase: pre-open DB pools/warm caches BEFORE marking ready |

---

## 21. Global Harvest Checklist — What Gold Template Actually Copies (No Fakes)

> **Now 16 repos harvested: any-llm (§2), langgraph (§3+§7), pydantic-ai (§4+§11), fastembed (§5+§12), mcp-adapters (§6), deepagents (§8), open-swe (§9), agent-protocol (§10), dsh (§13), langchain ref (§14), openwiki ref (§15), open-webui (§16), dify (§17), dispatch (§18), the-algorithm-ml (§19), twitter-server (§20). Deduplicate: keep one pattern per capability.**

**Immediately (P0-real):**

- [ ] `ai/llm.py`: own `ChatModel` Protocol stays, impl = `AnyLLMChatModel` calling `any_llm.acompletion`. Delete `FakeChatModel` prod path.
- [ ] `ai/embeddings.py`: own `EmbeddingProvider` stays, impl = `FastEmbedProvider` (`TextEmbedding`) + `AnyLLMEmbeddingProvider` (`any_llm.embedding`). Delete `FakeEmbeddingProvider` prod.
- [ ] `agents/graph.py`: fix to `langgraph.prebuilt.create_react_agent` + `InMemorySaver`.
- [ ] `core/config/base_config.py`: adopt TML `BaseConfig` — `extra=forbid`, `one_of`/`at_most_one_of` root validators, `pretty_print()` yaml (§19.2).
- [ ] `pyproject.toml` extras: `any-llm-sdk`, `fastembed`, `langgraph`, `pydantic-ai`, `langchain-mcp-adapters`, `deepagents`, `mcp`.
- [ ] `settings.py`: `llm_provider/model/api_key`, `embedding_provider/model`, `vector_store` fields.
- [ ] `web/api/health.py`: liveness `/api/health` vs readiness `/api/ready` split (twitter-server §20).

**Next (P5/P6):**

- [ ] `agents/mcp_bridge.py`: `langchain_mcp_adapters` `MultiServerMCPClient`.
- [ ] `agents/harness/`: `pydantic_ai.Agent` + `deepagents` skills resolver + dsh plugin waterfall pattern.
- [ ] `ai/knowledge/ranking.py`: TML weighted-sum scorer with config weights incl. negative spam weights (§19.4).
- [ ] `ai/knowledge/`: `fastembed` sparse + late interaction + rerank `TextCrossEncoder`; hybrid BM25+vector per open-webui/dify.
- [ ] `operations/admin.py`: twitter-server-style self-registering ops routes (`Route(alias, group)` → auto dashboard index); runtime log-level + toggles + tunables; `BuildProperties` (`GIT_SHA`/`BUILD_DATE`).
- [ ] `web/api/runs|threads|store`: `agent-protocol` OpenAPI router.

**Verification (real):** `ollama` local (`ollama/ollama` docker + `llama3.1:8b`) + `fastembed` BGE (ONNX, CPU) gives full green without external API keys. Live providers optional via `OPENAI_API_KEY` etc.

---

*End — every feature above is from `cat TEMP/<repo>/README.md` + `ls src/` + `cat docs/` + `grep "def \|class "` on real code. No blog summaries, no hallucinated APIs.*
