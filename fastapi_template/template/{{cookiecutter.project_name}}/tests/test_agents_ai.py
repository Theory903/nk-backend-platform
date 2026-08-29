import pytest

from {{cookiecutter.project_name}}.ai.embeddings import get_embedding_provider
from {{cookiecutter.project_name}}.ai.llm import (
    AssistantReply,
    ChatModel,
    Message,
    ToolCall,
    ToolSpec,
    get_chat_model,
)
from tests._fakes import FakeChatModel, FakeEmbeddingProvider, ScriptedEmbeddingProvider


async def test_fake_model_replays_scripted_replies() -> None:
    """
    The fake model yields scripted replies in order and records prompts.
    """
    model = FakeChatModel(
        [
            AssistantReply(
                content=None,
                tool_calls=[ToolCall(id="call_1", name="echo", arguments={"text": "hi"})],
            ),
            AssistantReply(content="done", tool_calls=[]),
        ],
    )
    tools = [
        ToolSpec(
            name="echo",
            description="Echo text back",
            parameters={"type": "object", "properties": {}},
        ),
    ]

    first = await model.complete(
        [Message(role="user", content="say hi")],
        tools=tools,
    )
    second = await model.complete([Message(role="user", content="again")], tools=tools)

    assert first.tool_calls[0].name == "echo"
    assert second.content == "done"
    assert model.requests[1][-1].content == "again"
    assert isinstance(model, ChatModel)


def test_unknown_provider_raises_helpful_error() -> None:
    """
    Unconfigured providers fail with the provider name in the message.
    """
    with pytest.raises(ValueError, match="does-not-exist"):
        get_chat_model("does-not-exist")


def test_embeddings_are_deterministic_and_normalized() -> None:
    """
    Scripted embeddings are stable per input and usable as vectors.
    """
    provider = FakeEmbeddingProvider()
    assert isinstance(provider, FakeEmbeddingProvider)

    first = provider.embed("hello")
    second = provider.embed("hello")

    assert first == second
    assert len(first) > 0
    assert all(-1.0 <= value <= 1.0 for value in first)

    scripted = ScriptedEmbeddingProvider()
    assert len(scripted.embed("x")) == scripted.dimensions


def test_fake_embedding_provider_name_rejected_from_factory() -> None:
    with pytest.raises(ValueError, match="fake"):
        get_embedding_provider("fake")
