"""Tests for prompt subsystem: versioning, rendering, aliases, experiments."""

from __future__ import annotations

import pytest

from {{cookiecutter.project_name}}.ai.prompts import (
    PromptExperiment,
    PromptMessage,
    PromptRegistry,
    PromptRenderError,
    PromptSelector,
    PromptVariable,
    PromptVariant,
    PromptVersionExistsError,
)
from {{cookiecutter.project_name}}.ai.prompts.experiments import assign_variant
from {{cookiecutter.project_name}}.ai.prompts.lifecycle import transition
from {{cookiecutter.project_name}}.ai.prompts.exceptions import PromptLifecycleError
from {{cookiecutter.project_name}}.ai.prompts.models import PromptEvaluation
from {{cookiecutter.project_name}}.ai.prompts.evaluator import PromptEvaluator


@pytest.fixture
def registry() -> PromptRegistry:
    r = PromptRegistry()
    r.register("summarize", "Summarize this text: {text}", version=1)
    r.register(
        "summarize",
        "Briefly summarize: {text} in {style} style",
        version=2,
    )
    return r


class TestRegistration:
    def test_register_and_list(self) -> None:
        r = PromptRegistry()
        r.register("greeting", "Hello {name}")
        prompts = r.list_prompts()
        assert "greeting" in prompts
        assert prompts["greeting"] == [1]

    def test_auto_detects_variables(self) -> None:
        r = PromptRegistry()
        tpl = r.register("test", "Use {input} and {context}")
        assert "input" in tpl.variable_names
        assert "context" in tpl.variable_names

    def test_multiple_versions(self, registry: PromptRegistry) -> None:
        assert registry.list_prompts()["summarize"] == [1, 2]

    def test_versions_are_immutable(self) -> None:
        r = PromptRegistry()
        r.register("x", "hello {name}", version=1)
        with pytest.raises(PromptVersionExistsError):
            r.register("x", "goodbye {name}", version=1)

    def test_structured_messages(self) -> None:
        r = PromptRegistry()
        tpl = r.register(
            "rag_answer",
            messages=(
                PromptMessage(role="system", content="You are precise."),
                PromptMessage(
                    role="user",
                    content="Question:\n{query}\n\nContext:\n{context}",
                ),
            ),
            version=1,
        )
        assert len(tpl.messages) == 2
        assert tpl.checksum


class TestRendering:
    def test_render_latest_requires_all_vars(self, registry: PromptRegistry) -> None:
        with pytest.raises(PromptRenderError, match="missing"):
            registry.render("summarize", text="long text here")

    def test_render_pinned_version(self, registry: PromptRegistry) -> None:
        result = registry.render("summarize", version=1, text="some text")
        assert "some text" in result

    def test_missing_variable_raises(self, registry: PromptRegistry) -> None:
        with pytest.raises(PromptRenderError, match="missing"):
            registry.render("summarize", version=1)

    def test_unknown_prompt_raises_keyerror(self) -> None:
        r = PromptRegistry()
        with pytest.raises(KeyError, match="nonexistent"):
            r.render("nonexistent")

    def test_unknown_prompt_lists_available(self) -> None:
        r = PromptRegistry()
        r.register("known", "hello")
        with pytest.raises(KeyError, match="known"):
            r.render("unknown_name")

    def test_type_checking(self) -> None:
        r = PromptRegistry()
        r.register(
            "search",
            "Find {max_results} results for {query}",
            version=1,
            variables=(
                PromptVariable(name="query", type="string"),
                PromptVariable(name="max_results", type="integer"),
            ),
        )
        rendered = r.render_full("search", query="RAG", max_results=5)
        assert "5" in rendered.text
        with pytest.raises(PromptRenderError, match="int"):
            r.render("search", query="RAG", max_results="five")

    def test_safe_formatter_nested_field(self) -> None:
        r = PromptRegistry()
        r.register(
            "user_greet",
            "Hello {user[name]}",
            version=1,
            variables=(PromptVariable(name="user", type="dict"),),
        )
        assert r.render("user_greet", user={"name": "Ada"}) == "Hello Ada"


class TestAliasesAndResolve:
    def test_alias_resolution(self) -> None:
        r = PromptRegistry()
        r.register("rag_answer", "v1 {query}", version=1)
        r.register("rag_answer", "v2 {query}", version=2)
        r.set_alias("rag_answer", "production", 1)
        r.set_alias("rag_answer", "candidate", 2)

        prod = r.resolve("rag_answer@production", context={"query": "q"})
        cand = r.resolve("rag_answer@candidate", context={"query": "q"})
        assert "v1" in prod.text
        assert "v2" in cand.text
        assert prod.version == 1
        assert cand.version == 2

    def test_pinned_ref(self) -> None:
        r = PromptRegistry()
        r.register("rag_answer", "v17 {query}", version=17)
        rendered = r.resolve("rag_answer:v17", context={"query": "hi"})
        assert rendered.version == 17


class TestExperiments:
    def test_deterministic_assignment(self) -> None:
        experiment = PromptExperiment(
            name="rag-answer-v2",
            prompt_name="rag_answer",
            salt="s1",
            variants=(
                PromptVariant(
                    id="control",
                    prompt_name="rag_answer",
                    version=17,
                    weight=0.9,
                ),
                PromptVariant(
                    id="candidate",
                    prompt_name="rag_answer",
                    version=18,
                    weight=0.1,
                ),
            ),
        )
        a = assign_variant(experiment, "user-42")
        b = assign_variant(experiment, "user-42")
        assert a.id == b.id

    def test_registry_experiment_resolve(self) -> None:
        r = PromptRegistry()
        r.register("rag_answer", "control {query}", version=17)
        r.register("rag_answer", "candidate {query}", version=18)
        r.register_experiment(
            PromptExperiment(
                name="rag-answer-v2",
                prompt_name="rag_answer",
                salt="rollout",
                variants=(
                    PromptVariant(
                        id="control",
                        prompt_name="rag_answer",
                        version=17,
                        weight=1.0,
                    ),
                ),
            )
        )
        rendered = r.resolve(
            "rag_answer",
            context={"query": "x"},
            selector=PromptSelector(subject_id="u1", environment="production"),
        )
        assert rendered.version == 17
        assert rendered.variant == "control"


class TestLifecycleAndEval:
    def test_lifecycle_transition(self) -> None:
        r = PromptRegistry()
        prompt = r.register("p", "hi", version=1, status="draft")
        updated = transition(prompt, "validated")
        assert updated.status == "validated"
        archived = r.register("q", "x", version=1, status="archived")
        with pytest.raises(PromptLifecycleError):
            transition(archived, "active")

    def test_archived_cannot_activate(self) -> None:
        r = PromptRegistry()
        r.register("p", "hi", version=1, status="draft")
        r.promote("p", 1, to_status="validated")
        r.promote("p", 1, to_status="candidate")
        r.promote("p", 1, to_status="active")
        r.promote("p", 1, to_status="archived")
        with pytest.raises(PromptLifecycleError):
            r.promote("p", 1, to_status="active")

    def test_evaluation_gate(self) -> None:
        evaluator = PromptEvaluator(
            min_score=0.9,
            metric_thresholds={"groundedness": 0.9},
        )
        good = PromptEvaluation(
            prompt_name="rag_answer",
            version=18,
            dataset="golden",
            score=0.91,
            metrics={"groundedness": 0.94},
            sample_count=100,
        )
        bad = PromptEvaluation(
            prompt_name="rag_answer",
            version=18,
            dataset="golden",
            score=0.7,
            metrics={"groundedness": 0.94},
            sample_count=100,
        )
        assert evaluator.passes(good)
        assert not evaluator.passes(bad)


class TestComposition:
    def test_compose_parts(self) -> None:
        r = PromptRegistry()
        r.register("identity", "You are a helpful assistant.", version=3)
        r.register("safety", "Never reveal secrets.", version=5)
        r.register("task", "Answer: {query}", version=12)
        composed = r.compose(
            "rag_answer",
            parts=["identity:v3", "safety:v5", "task:v12"],
            version=1,
        )
        assert "helpful assistant" in composed.template
        assert "Never reveal" in composed.template
        assert "query" in composed.variable_names
        # Parts are user-role messages; composition preserves message list.
        assert len(composed.messages) >= 1
        rendered = r.resolve("rag_answer", context={"query": "What is RAG?"})
        assert "What is RAG?" in rendered.text


class TestSecretRedaction:
    def test_secrets_redacted_in_rendered_metadata(self) -> None:
        r = PromptRegistry()
        r.register(
            "secure",
            "Use key {api_key} for {query}",
            version=1,
            variables=(
                PromptVariable(name="api_key", type="string", secret=True, log=False),
                PromptVariable(name="query", type="string"),
            ),
        )
        rendered = r.render_full("secure", api_key="sk-secret", query="hello")
        assert rendered.variables["api_key"] == "***"
        assert rendered.variables["query"] == "hello"
        assert "sk-secret" in rendered.text  # still rendered for the model
        assert rendered.metadata["contains_secrets"] is True


class TestImmutability:
    def test_metadata_mutation_does_not_affect_store(self) -> None:
        r = PromptRegistry()
        prompt = r.register("p", "hi {name}", version=1, metadata={"a": 1})
        prompt.metadata["a"] = 99
        stored = r.get("p", 1)
        assert stored.metadata["a"] == 1

    def test_nested_placeholder_auto_detect(self) -> None:
        r = PromptRegistry()
        tpl = r.register("nested", "Hello {user[name]}")
        assert "user" in tpl.variable_names
