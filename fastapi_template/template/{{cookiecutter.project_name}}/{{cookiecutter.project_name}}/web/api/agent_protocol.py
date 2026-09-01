"""Minimal durable-shaped agent run and thread HTTP contract."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.factory import AgentRuntimeFactory
from {{cookiecutter.project_name}}.agents.runtime import (
    BoundedRuntime,
    RuntimeLimits,
    RuntimeStep,
    StateCheckpointStore,
)
from {{cookiecutter.project_name}}.agents.security import SecurityPipeline
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.ai.gateway.router import get_router
from {{cookiecutter.project_name}}.identity.deps import CurrentUser
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.platform.contracts import Scope, WorkflowState

router = APIRouter(dependencies=[Depends(CurrentUser)])
mcp_router = APIRouter(dependencies=[Depends(CurrentUser)])


class RunRequest(BaseModel):
    """Input for an agent execution."""

    input: str = Field(min_length=1, max_length=100_000)
    thread_id: str | None = None
    resume_workflow_id: str | None = None
    runtime_mode: str = Field(
        default="auto",
        description="loop | graph | supervisor | auto",
    )


class RunResponse(BaseModel):
    """Stable run result envelope."""

    run_id: str
    thread_id: str
    content: str | None
    steps: int


async def _run_secure(
    payload: RunRequest,
    request: Request,
) -> tuple[WorkflowState, str | None]:
    scope = getattr(request.state, "scope", None)
    thread_id = payload.thread_id or f"thread_{uuid.uuid4().hex}"
    if isinstance(scope, Scope):
        scope = scope.model_copy(update={"thread_id": thread_id})
        request.state.scope = scope
    if not isinstance(scope, Scope):
        principal = getattr(request.state, "principal", None)
        if isinstance(principal, Principal) and principal.is_authenticated:
            scope = Scope(
                principal_id=principal.user_id,
                organization_id=principal.org_id or f"personal:{principal.user_id}",
                thread_id=thread_id,
            )
            request.state.scope = scope
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")

    security = getattr(request.app.state, "security_pipeline", None) or SecurityPipeline()
    inspection = security.inspect_prompt(payload.input)
    if not inspection.allowed:
        raise HTTPException(
            status_code=400,
            detail=f"prompt rejected: {', '.join(inspection.reasons)}",
        )

    model = get_router().model_for()
    tools = getattr(request.app.state, "tool_registry", None) or ToolRegistry()
    gateway = getattr(request.app.state, "tool_gateway", None)
    session_runtime = getattr(request.app.state, "session_runtime", None)
    resolved_mode = AgentRuntimeFactory.resolve_mode(
        payload.runtime_mode,
        task=inspection.sanitized,
        tools=tools,
    )
    session_run_id: str | None = None
    recorder = None
    if session_runtime is not None:
        run_uuid, recorder = await session_runtime.start_run(
            scope,
            thread_id=thread_id,
            task=inspection.sanitized,
            runtime_mode=payload.runtime_mode,
        )
        session_run_id = str(run_uuid)
        await recorder.context_built(
            task=inspection.sanitized,
            runtime_mode=str(resolved_mode),
        )

    agent_runtime = AgentRuntimeFactory.create(
        payload.runtime_mode,
        model=model,
        tools=tools,
        scope=scope,
        task=inspection.sanitized,
        security=security,
        gateway=gateway,
        recorder=recorder,
    )
    checkpoint_store = getattr(request.app.state, "agent_checkpoint_store", None)
    if checkpoint_store is None:
        state_store = getattr(request.app.state, "state_store", None)
        if state_store is None:
            raise HTTPException(
                status_code=503,
                detail="durable agent state store is not configured",
            )
        checkpoint_store = StateCheckpointStore(state_store, scope)

    async def handle(
        state: WorkflowState,
        step: RuntimeStep,
    ) -> WorkflowState:
        if step is RuntimeStep.REASON and "content" not in state.data:
            task = str(state.data.get("task", inspection.sanitized))
            try:
                result = await agent_runtime.run(task)
            except Exception as exc:
                if session_runtime is not None and session_run_id is not None:
                    await session_runtime.fail_run(
                        scope,
                        UUID(session_run_id),
                        error=str(exc),
                        thread_id=thread_id,
                    )
                raise
            state.data["content"] = security.finalize_output(result.content or "")
            state.data["steps"] = result.steps
            state.data["runtime_mode"] = str(
                getattr(result, "runtime_mode", resolved_mode),
            )
            if session_runtime is not None and session_run_id is not None:
                await session_runtime.complete_run(
                    scope,
                    UUID(session_run_id),
                    content=state.data["content"],
                    steps=int(state.data["steps"]),
                    workflow_id=state.workflow_id,
                    runtime_mode=state.data["runtime_mode"],
                )
        return state

    workflow_runtime = BoundedRuntime(
        scope=scope,
        handler=handle,
        limits=RuntimeLimits(max_cycles=1, max_retries=0),
        checkpoints=checkpoint_store,
    )
    if payload.resume_workflow_id:
        try:
            UUID(payload.resume_workflow_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="resume_workflow_id must be a UUID",
            ) from exc
        resumed = await checkpoint_store.load(payload.resume_workflow_id)
        if resumed is None:
            raise HTTPException(status_code=404, detail="workflow checkpoint not found")
        state = await workflow_runtime.run(state=resumed)
        return state, session_run_id
    state = await workflow_runtime.run(
        state=WorkflowState(
            scope=scope,
            data={"task": inspection.sanitized},
        ),
    )
    return state, session_run_id


@router.post("/v1/runs", response_model=RunResponse)
async def create_run(payload: RunRequest, request: Request) -> RunResponse:
    """Execute a bounded agent run and return its verified result."""
    if payload.resume_workflow_id and not payload.thread_id:
        raise HTTPException(
            status_code=400,
            detail="thread_id is required when resuming a workflow",
        )
    thread_id = payload.thread_id or f"thread_{uuid.uuid4().hex}"
    payload = payload.model_copy(update={"thread_id": thread_id})
    state, session_run_id = await _run_secure(payload, request)
    run_id = session_run_id or str(state.workflow_id)
    content = str(state.data.get("content", ""))
    request.app.state.last_agent_run = {
        "run_id": run_id,
        "thread_id": thread_id,
        "steps": int(state.data.get("steps", 0)),
    }
    return RunResponse(
        run_id=run_id,
        thread_id=thread_id,
        content=content,
        steps=int(state.data.get("steps", 0)),
    )


@router.post("/v1/runs/stream")
async def stream_run(payload: RunRequest, request: Request) -> StreamingResponse:
    """Stream a final result using SSE without coupling to a model SDK."""
    if payload.resume_workflow_id and not payload.thread_id:
        raise HTTPException(
            status_code=400,
            detail="thread_id is required when resuming a workflow",
        )
    thread_id = payload.thread_id or f"thread_{uuid.uuid4().hex}"
    payload = payload.model_copy(update={"thread_id": thread_id})
    state, session_run_id = await _run_secure(payload, request)
    run_id = session_run_id or str(state.workflow_id)
    request.app.state.last_agent_run = {
        "run_id": run_id,
        "thread_id": thread_id,
        "steps": int(state.data.get("steps", 0)),
    }

    async def events() -> AsyncIterator[str]:
        result = {
            "run_id": run_id,
            "thread_id": thread_id,
            "content": state.data.get("content", ""),
            "steps": state.data.get("steps", 0),
        }
        yield f"event: result\ndata: {json.dumps(result)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/v1/runs/{run_id}")
async def inspect_run(run_id: str, request: Request) -> dict[str, object]:
    """Inspect a durable run's metadata and append-only event stream."""
    scope = getattr(request.state, "scope", None)
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")
    session_runtime = getattr(request.app.state, "session_runtime", None)
    if session_runtime is None:
        raise HTTPException(status_code=503, detail="session runtime is not configured")
    try:
        run_uuid = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id must be a UUID") from exc
    return await session_runtime.inspect(scope, run_uuid)


@router.get("/v1/runs/{run_id}/events")
async def list_run_events(run_id: str, request: Request) -> dict[str, object]:
    """Return append-only session events for replay."""
    scope = getattr(request.state, "scope", None)
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")
    session_runtime = getattr(request.app.state, "session_runtime", None)
    if session_runtime is None:
        raise HTTPException(status_code=503, detail="session runtime is not configured")
    try:
        run_uuid = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id must be a UUID") from exc
    events = await session_runtime.replay(scope, run_uuid)
    return {
        "run_id": run_id,
        "events": [event.model_dump(mode="json") for event in events],
    }


class ForkRequest(BaseModel):
    through_sequence: int | None = Field(
        default=None,
        ge=0,
        description="Copy events up to and including this sequence number",
    )


@router.post("/v1/runs/{run_id}/fork")
async def fork_run(
    run_id: str,
    request: Request,
    body: ForkRequest | None = None,
) -> dict[str, str]:
    """Fork a run by copying its event stream into a new run id."""
    scope = getattr(request.state, "scope", None)
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")
    session_runtime = getattr(request.app.state, "session_runtime", None)
    if session_runtime is None:
        raise HTTPException(status_code=503, detail="session runtime is not configured")
    try:
        run_uuid = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id must be a UUID") from exc
    through = body.through_sequence if body is not None else None
    try:
        new_run_id = await session_runtime.fork(
            scope,
            run_uuid,
            through_sequence=through,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": str(new_run_id), "parent_run_id": run_id}


@router.get("/v1/runs/{run_id}/resume")
async def resume_run_context(run_id: str, request: Request) -> dict[str, object]:
    """Return resume hints (task, thread, workflow checkpoint) for a run."""
    scope = getattr(request.state, "scope", None)
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")
    session_runtime = getattr(request.app.state, "session_runtime", None)
    if session_runtime is None:
        raise HTTPException(status_code=503, detail="session runtime is not configured")
    try:
        run_uuid = UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id must be a UUID") from exc
    try:
        return await session_runtime.resume_context(scope, run_uuid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v1/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    principal: Principal = Depends(CurrentUser),
) -> dict[str, str]:
    """Return a thread identity; persistence is supplied by the store adapter."""
    return {"thread_id": thread_id, "status": "active"}


@router.get("/mcp")
async def mcp_capabilities(request: Request) -> dict[str, object]:
    """Expose the MCP-compatible capability discovery document."""
    registry = getattr(request.app.state, "tool_registry", None)
    return {
        "protocol": "2025-06-18",
        "server": {"name": "{{cookiecutter.project_name}}", "version": "1"},
        "capabilities": {"tools": {"listChanged": False}},
        "tools": _mcp_tools(registry),
    }


def _mcp_tools(registry: ToolRegistry | None = None) -> list[dict[str, object]]:
    """Return built-in MCP tools plus registered agent tools."""
    tools: list[dict[str, object]] = [
        {
            "name": "health",
            "description": "Return service health.",
            "inputSchema": {"type": "object", "additionalProperties": False},
        },
        {
            "name": "build_info",
            "description": "Return immutable build metadata.",
            "inputSchema": {"type": "object", "additionalProperties": False},
        },
    ]
    if registry is not None:
        for tool in registry.all():
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.parameters,
                },
            )
    return tools


@router.post("/mcp")
async def mcp_request(
    payload: dict[str, object],
    request: Request,
) -> dict[str, object]:
    """Handle JSON-RPC requests for MCP tool discovery and dispatch."""
    method = str(payload.get("method", ""))
    request_id = payload.get("id")
    registry = getattr(request.app.state, "tool_registry", None) or ToolRegistry()
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": _mcp_tools(registry)},
        }
    if method in {"ping", "notifications/initialized"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/call":
        params = payload.get("params")
        if not isinstance(params, dict) or "name" not in params:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "unknown or invalid tool"},
            }
        name = str(params["name"])
        allowed = {"health", "build_info", *registry.names()}
        if name not in allowed:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "unknown or invalid tool"},
            }
        if name == "health":
            result: object = {"status": "ok"}
            text = json.dumps(result)
        elif name == "build_info":
            result = {
                "service": "{{cookiecutter.project_name}}",
                "version": getattr(request.app.state, "service_version", "0.1.0"),
                "git_sha": getattr(request.app.state, "git_sha", "unknown"),
            }
            text = json.dumps(result)
        else:
            arguments = params.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            scope = getattr(request.state, "scope", None)
            if not isinstance(scope, Scope):
                scope = Scope(principal_id="mcp", organization_id="system")
            gateway = getattr(request.app.state, "tool_gateway", None)
            if gateway is not None:
                result = await gateway.invoke(name, arguments, scope)
                text = result.output
            else:
                text = await registry.dispatch(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "method not available"},
    }


@mcp_router.get("")
async def mcp_root_capabilities(request: Request) -> dict[str, object]:
    return await mcp_capabilities(request)


@mcp_router.post("")
async def mcp_root_request(
    payload: dict[str, object],
    request: Request,
) -> dict[str, object]:
    return await mcp_request(payload, request)


__all__ = ["mcp_router", "router"]
