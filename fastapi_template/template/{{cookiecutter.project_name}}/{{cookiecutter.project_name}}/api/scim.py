from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response, status
from fastapi.responses import JSONResponse

from ..identity.deps import RequirePermission
from ..core.scim import (
    ScimError,
    ScimErrorResponse,
    ScimListResponse,
    ScimPatchRequest,
    ScimUser,
)
from ..core.scim_filter import ScimFilterError, ScimFilterParser
from ..services.scim import ScimService

router = APIRouter(
    prefix="/scim/v2",
    tags=["SCIM"],
    dependencies=[Depends(RequirePermission("identity.provision"))],
)


def get_scim_service() -> ScimService:
    """
    Replace with your DI container / tenant-aware dependency.
    """
    raise NotImplementedError


@router.post(
    "/Users",
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    user: ScimUser,
    service: Annotated[ScimService, Depends(get_scim_service)],
) -> ScimUser:
    return await service.create(user)


@router.get(
    "/Users/{user_id}",
)
async def get_user(
    user_id: str,
    service: Annotated[ScimService, Depends(get_scim_service)],
) -> ScimUser:
    return await service.get(user_id)


@router.put(
    "/Users/{user_id}",
)
async def replace_user(
    user_id: str,
    user: ScimUser,
    service: Annotated[ScimService, Depends(get_scim_service)],
) -> ScimUser:
    return await service.replace(
        user_id,
        user,
    )


@router.patch(
    "/Users/{user_id}",
)
async def patch_user(
    user_id: str,
    patch: ScimPatchRequest,
    service: Annotated[ScimService, Depends(get_scim_service)],
) -> ScimUser:
    return await service.patch(
        user_id,
        patch.Operations,
    )


@router.delete(
    "/Users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user(
    user_id: str,
    service: Annotated[ScimService, Depends(get_scim_service)],
) -> Response:
    await service.delete(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/Users",
)
async def list_users(
    service: Annotated[ScimService, Depends(get_scim_service)],
    filter: str | None = Query(default=None),
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=0, le=1000),
) -> ScimListResponse:
    parsed_filter = None

    if filter:
        try:
            parsed_filter = ScimFilterParser(filter).parse()
        except ScimFilterError as exc:
            raise ScimError(
                str(exc),
                status_code=400,
                scim_type="invalidFilter",
            ) from exc

    return await service.list(
        filter_expression=parsed_filter,
        start_index=startIndex,
        count=count,
    )


def register_scim(app: FastAPI) -> None:
    """Mount SCIM routes and register SCIM error handlers on the app."""
    app.include_router(router)

    async def handle_scim_error(
        request: Request,
        exc: ScimError,
    ) -> JSONResponse:
        body = ScimErrorResponse(
            status=str(exc.status_code),
            detail=exc.detail,
            scimType=exc.scim_type,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=body.model_dump(exclude_none=True),
            media_type="application/scim+json",
        )

    app.add_exception_handler(
        ScimError,
        handle_scim_error,
    )


__all__ = [
    "get_scim_service",
    "register_scim",
    "router",
]
