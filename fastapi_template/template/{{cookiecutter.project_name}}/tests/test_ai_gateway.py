from {{cookiecutter.project_name}}.ai.gateway.router import ModelRouter, Route
from {{cookiecutter.project_name}}.ai.usage import UsageTracker


def test_router_default_and_reasoning() -> None:
    router = ModelRouter(
        routes={
            "chat": Route(provider="ollama", model="llama3.2"),
            "reasoning": Route(provider="openai", model="gpt-4o"),
        },
        task_aliases={"default": "chat"},
    )
    assert router.for_task("default").provider == "ollama"
    assert router.for_capability("reasoning").model == "gpt-4o"
    assert router.for_task("unknown").provider == "ollama"


def test_usage_tracker_record_and_get() -> None:
    tracker = UsageTracker()
    tracker.record("openai", prompt_tokens=10, completion_tokens=20, cost=0.01)
    rec = tracker.get("openai")
    assert rec.prompt_tokens == 10
    assert rec.completion_tokens == 20
    assert rec.cost_usd == 0.01
    assert rec.calls == 1
    tracker.record("openai", prompt_tokens=5, completion_tokens=5)
    assert tracker.get("openai").calls == 2
    assert len(tracker.all()) == 1
    tracker.reset()
    assert tracker.all() == {}
