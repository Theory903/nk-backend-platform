import pytest

from {{cookiecutter.project_name}}.workflows import Step, Workflow, WorkflowRunner


def _make_workflow(**kwargs) -> Workflow:
    wf = Workflow(name="test_flow")
    wf.add_step(Step(name="fetch", fn=lambda ctx: ctx.get("url", "data")))
    return wf


@pytest.mark.asyncio
async def test_simple_completion() -> None:
    wf = Workflow(name="flow")
    wf.add_step(Step(name="step_a", fn=lambda ctx: "value_a"))
    runner = WorkflowRunner()
    result = await runner.run(wf)
    assert result.ok
    assert result.completed_steps == ["step_a"]
    assert result.outputs["step_a"] == "value_a"


@pytest.mark.asyncio
async def test_retry_then_success() -> None:
    attempts: list[int] = []

    def flaky(ctx) -> str:
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("transient")
        return "ok"

    wf = Workflow(name="retry_flow")
    wf.add_step(Step(name="flaky_step", fn=flaky, max_retries=3))
    runner = WorkflowRunner()
    result = await runner.run(wf)
    assert result.ok
    assert result.outputs["flaky_step"] == "ok"


@pytest.mark.asyncio
async def test_failure_triggers_compensation() -> None:
    undone: list[str] = []

    def do_reserve(ctx) -> str:
        return "reserved"

    def undo_reserve(ctx) -> None:
        undone.append("reserve_undone")

    def fail(ctx) -> str:
        raise RuntimeError("boom")

    wf = Workflow(name="saga")
    wf.add_step(Step(name="reserve", fn=do_reserve, compensate=undo_reserve))
    wf.add_step(Step(name="charge", fn=fail))
    runner = WorkflowRunner()
    result = await runner.run(wf)
    assert not result.ok
    assert result.failed_step == "charge"
    assert undone == ["reserve_undone"]


@pytest.mark.asyncio
async def test_hitl_approval_gate() -> None:
    async def approve(step, ctx) -> bool:
        return False

    wf = Workflow(name="gated")
    wf.add_step(Step(name="deploy", fn=lambda ctx: "done", requires_approval=True))
    runner = WorkflowRunner(approve_fn=approve)
    result = await runner.run(wf)
    assert not result.ok
    assert result.status == "rejected"
    assert result.error and "approval denied" in result.error


def test_validate_empty_workflow() -> None:
    wf = Workflow(name="empty")
    errors = wf.validate()
    assert any("no steps" in e for e in errors)
