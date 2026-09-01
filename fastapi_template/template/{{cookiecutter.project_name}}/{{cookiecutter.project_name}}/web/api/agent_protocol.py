"""Minimal durable-shaped agent run and thread HTTP contract."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.agents.loop import LoopRuntime
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


class RunResponse(BaseModel):
    """Stable run result envelope."""

    run_id: str
    thread_id: str
    content: str | None
    steps: int


async def _run_secure(
    payload: RunRequest,
    request: Request,
) -> WorkflowState:
    scope = getattr(request.state, "scope", None)
    if isinstance(scope, Scope) and payload.thread_id:
        scope = scope.model_copy(update={"thread_id": payload.thread_id})
        request.state.scope = scope
    if not isinstance(scope, Scope):
        principal = getattr(request.state, "principal", None)
        if isinstance(principal, Principal) and principal.is_authenticated:
            scope = Scope(
                principal_id=principal.user_id,
                organization_id=principal.org_id or f"personal:{principal.user_id}",
                thread_id=payload.thread_id,
            )
            request.state.scope = scope
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")

    security = SecurityPipeline()
    inspection = security.inspect_prompt(payload.input)
    if not inspection.allowed:
        raise HTTPException(
            status_code=400,
            detail=f"prompt rejected: {', '.join(inspection.reasons)}",
        )

    model = get_router().model_for()
    loop = LoopRuntime(
        model,
        ToolRegistry(),
        scope=scope,
        security=security,
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
            result = await loop.run(task)
            state.data["content"] = security.validate_output(result.content or "")
            state.data["steps"] = result.steps
        return state

    runtime = BoundedRuntime(
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
        return await runtime.run(state=resumed)
    return await runtime.run(
        state=WorkflowState(
            scope=scope,
            data={"task": inspection.sanitized},
        ),
    )


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
    state = await _run_secure(payload, request)
    run_id = str(state.workflow_id)
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
    state = await _run_secure(payload, request)
    run_id = str(state.workflow_id)
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


@router.get("/v1/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    principal: Principal = Depends(CurrentUser),
) -> dict[str, str]:
    """Return a thread identity; persistence is supplied by the store adapter."""
    return {"thread_id": thread_id, "status": "active"}


@router.get("/mcp")
async def mcp_capabilities() -> dict[str, object]:
    """Expose the MCP-compatible capability discovery document."""
    return {
        "protocol": "2025-06-18",
        "server": {"name": "{{cookiecutter.project_name}}", "version": "1"},
        "capabilities": {"tools": {"listChanged": False}},
        "tools": _mcp_tools(),
    }


def _mcp_tools() -> list[dict[str, object]]:
    """Return the deliberately small, read-only tool allowlist."""
    return [
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


@router.post("/mcp")
async def mcp_request(
    payload: dict[str, object],
    request: Request,
) -> dict[str, object]:
    """Handle JSON-RPC requests for the curated read-only MCP tool set."""
    method = str(payload.get("method", ""))
    request_id = payload.get("id")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": _mcp_tools()}}
    if method in {"ping", "notifications/initialized"}:
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/call":
        params = payload.get("params")
        if not isinstance(params, dict) or params.get("name") not in {
            "health",
            "build_info",
        }:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "unknown or invalid tool"},
            }
        name = str(params["name"])
        if name == "health":
            result: object = {"status": "ok"}
        else:
            result = {
                "service": "{{cookiecutter.project_name}}",
                "version": getattr(request.app.state, "service_version", "0.1.0"),
                "git_sha": getattr(request.app.state, "git_sha", "unknown"),
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "method not available"},
    }


@mcp_router.get("")
async def mcp_root_capabilities() -> dict[str, object]:
    return await mcp_capabilities()


@mcp_router.post("")
async def mcp_root_request(
    payload: dict[str, object],
    request: Request,
) -> dict[str, object]:
    return await mcp_request(payload, request)


__all__ = ["mcp_router", "router"]
