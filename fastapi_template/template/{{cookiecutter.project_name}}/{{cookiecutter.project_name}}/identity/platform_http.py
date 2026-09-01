"""Identity platform endpoints outside the database-specific adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from {{cookiecutter.project_name}}.identity.deps import (
    CurrentUser,
    RequireCsrf,
    RequirePermission,
    get_api_key_store,
    get_session_store,
    issue_csrf_token,
)
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.identity.permissions import has_permission

router = APIRouter(prefix="/auth", tags=["identity"])


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: set[str] = Field(default_factory=lambda: {"read"})
    ttl_days: int | None = Field(default=90, ge=1, le=3650)


class ApiKeyPublic(BaseModel):
    """Non-sensitive API-key metadata returned to callers."""

    key_id: str
    name: str
    owner_id: str | None = None
    org_id: str | None = None
    scopes: frozenset[str]
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


@router.get("/csrf")
def csrf_token(
    request: Request,
    principal: Principal = Depends(CurrentUser),
) -> dict[str, str]:
    """Return a CSRF token for browser cookie-authenticated mutations."""
    return {"token": issue_csrf_token(request)}


@router.get("/sessions")
def list_sessions(principal: Principal = Depends(CurrentUser)) -> list[dict[str, object]]:
    return [
        {
            "device_id": session.device_id,
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "expires_at": session.expires_at,
        }
        for session in get_session_store().list_for_principal(principal.user_id)
    ]


@router.delete("/sessions/{session_id}", dependencies=[Depends(CurrentUser), Depends(RequireCsrf())])
def revoke_session(
    session_id: str,
    principal: Principal = Depends(CurrentUser),
) -> dict[str, bool]:
    session = get_session_store().get_session(session_id, touch=False)
    if session is None or session.principal_id != principal.user_id:
        return {"revoked": False}
    return {"revoked": get_session_store().revoke(session_id)}


@router.post(
    "/api-keys",
    dependencies=[
        Depends(RequirePermission("identity.api_keys.write")),
        Depends(RequireCsrf()),
    ],
)
def create_api_key(
    payload: ApiKeyCreate,
    principal: Principal = Depends(CurrentUser),
) -> dict[str, object]:
    if principal.is_service:
        raise HTTPException(status_code=403, detail="service principals cannot mint API keys")
    if "*" in payload.scopes and "admin" not in principal.roles:
        raise HTTPException(status_code=403, detail="wildcard API-key scope requires admin role")
    if any(
        scope != "*" and not has_permission(principal, scope)
        for scope in payload.scopes
    ):
        raise HTTPException(
            status_code=403,
            detail="API-key scopes exceed the caller's permissions",
        )
    expires_at = (
        datetime.now(UTC) + timedelta(days=payload.ttl_days)
        if payload.ttl_days is not None
        else None
    )
    plaintext, record = get_api_key_store().create(
        payload.name,
        owner_id=principal.user_id,
        org_id=principal.org_id,
        scopes=payload.scopes,
        expires_at=expires_at,
    )
    return {"key": plaintext, "key_id": record.key_id, "name": record.name}


@router.get("/api-keys")
def list_api_keys(principal: Principal = Depends(CurrentUser)) -> list[ApiKeyPublic]:
    return [
        ApiKeyPublic(
            key_id=record.key_id,
            name=record.name,
            owner_id=record.owner_id,
            org_id=record.org_id,
            scopes=record.scopes,
            created_at=record.created_at,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
        )
        for record in get_api_key_store().list(owner_id=principal.user_id)
    ]


@router.delete("/api-keys/{key_id}", dependencies=[Depends(CurrentUser), Depends(RequireCsrf())])
def revoke_api_key(key_id: str, principal: Principal = Depends(CurrentUser)) -> dict[str, bool]:
    record = get_api_key_store().get(key_id)
    if record is None or record.owner_id != principal.user_id:
        return {"revoked": False}
    return {"revoked": get_api_key_store().revoke_by_id(key_id)}


__all__ = ["router"]
