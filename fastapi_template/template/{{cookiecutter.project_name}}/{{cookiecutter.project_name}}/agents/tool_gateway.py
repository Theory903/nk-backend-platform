"""Central tool gateway: policy, approval, audit, dispatch (P4)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from {{cookiecutter.project_name}}.observability.genai.metrics import record_tool_invoke
from {{cookiecutter.project_name}}.observability.genai.spans import tool_invoke_span
from {{cookiecutter.project_name}}.agents.security import SecurityPipeline, ToolPolicy
from {{cookiecutter.project_name}}.agents.tools import ToolRegistry
from {{cookiecutter.project_name}}.platform.contracts import (
    Scope,
    ToolDescriptor,
    ToolInvocation,
    ToolResult,
)
from {{cookiecutter.project_name}}.platform.audit import emit_audit

logger = logging.getLogger(__name__)

ApprovalHook = Any


def _validate_arguments(tool_parameters: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Basic JSON-schema required-field validation."""
    required = tool_parameters.get("required") or []
    if not isinstance(required, list):
        return None
    missing = [name for name in required if name not in arguments]
    if missing:
        return f"missing required arguments: {', '.join(missing)}"
    return None


class ToolGateway:
    """Single dispatch boundary for native, MCP, and feature-pack tools."""

    __slots__ = ("_registry", "_security", "_audit_enabled")

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        policy: ToolPolicy | None = None,
        security: SecurityPipeline | None = None,
        audit_enabled: bool = True,
    ) -> None:
        self._registry = registry
        self._security = security or SecurityPipeline(
            tool_policy=policy or ToolPolicy(),
        )
        self._audit_enabled = audit_enabled

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def security(self) -> SecurityPipeline:
        return self._security

    @property
    def policy(self) -> ToolPolicy:
        return self._security.tool_policy

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        scope: Scope,
        *,
        call_id: str | UUID | None = None,
        approval_hook: ApprovalHook | None = None,
    ) -> ToolResult:
        """Authorize, optionally approve, execute, and audit a tool call."""
        tool = self._registry.get(name)
        if tool is None:
            return ToolResult(
                call_id=_coerce_call_id(call_id),
                ok=False,
                output=f"unknown tool '{name}'",
                error_code="not_found",
            )

        validation_error = _validate_arguments(tool.parameters, arguments)
        if validation_error:
            result = ToolResult(
                call_id=_coerce_call_id(call_id),
                ok=False,
                output=validation_error,
                error_code="invalid_arguments",
            )
            await self._emit_audit(name, scope, outcome="invalid_arguments")
            return result

        descriptor = ToolDescriptor(
            name=tool.name,
            description=tool.description,
            input_schema=tool.parameters,
            risk=tool.risk,
            requires_approval=tool.requires_approval,
        )
        invocation = ToolInvocation(
            call_id=_coerce_call_id(call_id),
            descriptor=descriptor,
            arguments=dict(arguments),
            scope=scope,
        )
        decision = self._security.authorize_tool(invocation)
        if not decision.allowed:
            await self._emit_audit(
                name,
                scope,
                outcome="denied",
                detail={"reason": decision.reason},
            )
            return ToolResult(
                call_id=invocation.call_id,
                ok=False,
                output=f"DENIED: {decision.reason}",
                error_code="policy_denied",
            )

        if decision.requires_approval:
            approved = False
            if approval_hook is not None and callable(approval_hook):
                approved = bool(await approval_hook(invocation))
            if not approved:
                await self._emit_audit(
                    name,
                    scope,
                    outcome="approval_required",
                )
                return ToolResult(
                    call_id=invocation.call_id,
                    ok=False,
                    output="DENIED: tool invocation requires approval",
                    error_code="approval_required",
                )

        with tool_invoke_span(tool_name=name) as span_state:
            try:
                output = await self._registry.dispatch(name, arguments)
                await self._emit_audit(name, scope, outcome="success")
                record_tool_invoke(
                    tool_name=name,
                    duration_s=float(span_state.get("duration_s") or 0.0),
                    outcome="success",
                )
                return ToolResult(
                    call_id=invocation.call_id,
                    ok=True,
                    output=output,
                )
            except Exception as exc:
                logger.exception("tool %s failed", name)
                record_tool_invoke(
                    tool_name=name,
                    duration_s=float(span_state.get("duration_s") or 0.0),
                    outcome="error",
                )
                await self._emit_audit(
                    name,
                    scope,
                    outcome="error",
                    detail={"error": type(exc).__name__},
                )
                return ToolResult(
                    call_id=invocation.call_id,
                    ok=False,
                    output=str(exc),
                    error_code=type(exc).__name__,
                )

    async def dispatch_string(
        self,
        name: str,
        arguments: dict[str, Any],
        scope: Scope,
        *,
        call_id: str | UUID | None = None,
        approval_hook: ApprovalHook | None = None,
    ) -> str:
        """LoopRuntime-compatible dispatch returning a string observation."""
        result = await self.invoke(
            name,
            arguments,
            scope,
            call_id=call_id,
            approval_hook=approval_hook,
        )
        return result.output

    async def _emit_audit(
        self,
        tool_name: str,
        scope: Scope,
        *,
        outcome: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self._audit_enabled:
            return
        try:
            await emit_audit(
                "tool.invoke",
                actor_id=scope.principal_id,
                resource="tool",
                resource_id=tool_name,
                org_id=scope.organization_id,
                outcome=outcome,
                detail={"tool": tool_name, **(detail or {})},
            )
        except Exception:
            logger.exception("failed to emit tool audit event")


def _coerce_call_id(call_id: str | UUID | None) -> UUID:
    if isinstance(call_id, UUID):
        return call_id
    if isinstance(call_id, str) and call_id.strip():
        try:
            return UUID(call_id)
        except ValueError:
            pass
    return uuid4()


__all__ = ["ToolGateway"]
