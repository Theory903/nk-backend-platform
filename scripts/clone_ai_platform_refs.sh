#!/usr/bin/env bash
# Clone OSS references for the NK AI platform runtime (reference-only; no vendor copy).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${ROOT}/temp/oss"
mkdir -p "${DEST}"

clone_one() {
  local name="$1"
  local url="$2"
  local target="${DEST}/${name}"
  if [[ -d "${target}/.git" ]]; then
    echo "skip ${name} (exists)"
    return 0
  fi
  echo "clone ${name} ..."
  git clone --depth 1 "${url}" "${target}"
}

# ── Runtime dependencies (also published as pip packages) ──────────────────
clone_one langgraph           https://github.com/langchain-ai/langgraph.git
clone_one smolagents          https://github.com/huggingface/smolagents.git
clone_one haystack            https://github.com/deepset-ai/haystack.git
clone_one qdrant-client       https://github.com/qdrant/qdrant-client.git
clone_one python-sdk-mcp      https://github.com/modelcontextprotocol/python-sdk.git
clone_one a2a                 https://github.com/a2aproject/A2A.git
clone_one a2a-python          https://github.com/a2aproject/a2a-python.git
clone_one litellm             https://github.com/BerriAI/litellm.git
clone_one browser-use         https://github.com/browser-use/browser-use.git
clone_one ragas               https://github.com/explodinggradients/ragas.git
clone_one deepeval            https://github.com/confident-ai/deepeval.git
clone_one dspy                https://github.com/stanfordnlp/dspy.git

# ── Evaluation / harness references ───────────────────────────────────────
clone_one harness-evals       https://github.com/harness/harness-evals.git
clone_one promptfoo           https://github.com/promptfoo/promptfoo.git

# ── Code-agent / search / observability references ─────────────────────────
clone_one OpenHands           https://github.com/All-Hands-AI/OpenHands.git
clone_one searxng             https://github.com/searxng/searxng.git
clone_one semantic-conventions https://github.com/open-telemetry/semantic-conventions.git

# ── Architecture references (plugin/session/skills/research) ───────────────
clone_one deepseek-harness     https://github.com/deepseek-ai/deepseek-harness.git
clone_one gstack               https://github.com/garrytan/gstack.git

# ── Karpathy — reference + autoresearch (P26/P27) ───────────────────────────
clone_one autoresearch         https://github.com/karpathy/autoresearch.git
clone_one nanochat             https://github.com/karpathy/nanochat.git
clone_one nanoGPT              https://github.com/karpathy/nanoGPT.git
# microgpt: no standalone GitHub repo — minimal GPT patterns in nanochat / blog
clone_one llm.c                https://github.com/karpathy/llm.c.git
clone_one llama2.c             https://github.com/karpathy/llama2.c.git
clone_one micrograd            https://github.com/karpathy/micrograd.git
clone_one makemore             https://github.com/karpathy/makemore.git

echo "done → ${DEST}"
