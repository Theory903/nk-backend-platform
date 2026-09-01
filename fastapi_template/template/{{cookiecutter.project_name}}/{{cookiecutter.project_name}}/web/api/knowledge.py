"""Authorization-first knowledge answering endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from {{cookiecutter.project_name}}.ai.knowledge.answer import (
    AnswerRequest,
    AnswerResponse,
)
from {{cookiecutter.project_name}}.platform.contracts import Scope

router = APIRouter()


@router.post("/v1/answers", response_model=AnswerResponse)
async def answer_knowledge(
    payload: AnswerRequest,
    request: Request,
) -> AnswerResponse:
    """Answer only with a service wired by the application composition root."""
    scope = getattr(request.state, "scope", None)
    if scope is None:
        principal = getattr(request.state, "principal", None)
        if (
            principal is not None
            and not getattr(principal, "is_anonymous", True)
            and getattr(principal, "org_id", None)
        ):
            scope = Scope(
                principal_id=principal.user_id,
                organization_id=principal.org_id,
            )
    if not isinstance(scope, Scope):
        raise HTTPException(status_code=401, detail="authenticated scope required")
    service = getattr(request.app.state, "rag_service", None)
    if service is None or not callable(getattr(service, "answer", None)):
        raise HTTPException(status_code=503, detail="knowledge service unavailable")
    return await service.answer(payload.model_copy(update={"scope": scope}))


__all__ = ["answer_knowledge", "router"]
