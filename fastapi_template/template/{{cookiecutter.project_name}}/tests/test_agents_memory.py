from {{cookiecutter.project_name}}.agents.memory import MemoryStore


def test_working_memory_scoped_per_run() -> None:
    mem = MemoryStore()
    mem.push_working("run_1", {"role": "user", "content": "hi"})
    mem.push_working("run_2", {"role": "assistant", "content": "hello"})
    assert len(mem.get_working("run_1")) == 1
    assert mem.get_working("run_2")[0]["content"] == "hello"


def test_conversation_memory_limit() -> None:
    mem = MemoryStore()
    for i in range(10):
        mem.push_conversation("thread_a", {"i": i})
    assert len(mem.get_conversation("thread_a", limit=3)) == 3
    assert mem.get_conversation("thread_a", limit=3)[-1]["i"] == 9


def test_episodic_recall() -> None:
    mem = MemoryStore()
    mem.remember("u1", "likes pizza")
    mem.remember("u1", "has a dog")
    mem.remember("u2", "prefers tea")
    assert "dog" in mem.recall("u1")[0] or "pizza" in mem.recall("u1")[0]
    assert len(mem.recall("u1")) == 2
    assert len(mem.recall("u2")) == 1
