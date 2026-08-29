"""
Files HTTP API.

Responsibilities:
    - authenticated tenant-scoped uploads
    - bounded multipart uploads
    - object-storage abstraction
    - metadata registration
    - tenant ownership enforcement
    - presigned downloads
    - deletion
    - organization file listing

Security model:

    Principal
        |
        v
    TenantContext
        |
        v
    permission check
        |
        v
    FileRegistry ownership check
        |
        v
    ObjectStore

The client NEVER supplies the authoritative org_id.

For production:
    - use PostgreSQL for FileRegistry
    - use S3/MinIO for ObjectStore
    - use presigned URLs for large uploads/downloads
    - keep authorization before every object operation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from fastapi import (
    APIRouter,
    Depends,
    File as FileUpload,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict

from {{cookiecutter.project_name}}.core.errors import Problem
from {{cookiecutter.project_name}}.core.identifiers import new_id
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.platform.files import (
    LocalObjectStore,
    ObjectStore,
    new_file_key,
)


# ============================================================================
# Configuration
# ============================================================================


MAX_UPLOAD_BYTES = 50 * 1024 * 1024

DEFAULT_CONTENT_TYPE = "application/octet-stream"

ALLOWED_DOWNLOAD_TTL_S = 900


# ============================================================================
# Metadata
# ============================================================================


@dataclass
class FileMetadata:
    """
    Application-level file metadata.

    The object storage key is an internal implementation detail and should
    not normally be exposed to clients.
    """

    file_id: str
    key: str
    filename: str
    size: int
    content_type: str
    org_id: str
    uploaded_by: str = ""
    created_at: float = 0.0
    extra: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================================
# API models
# ============================================================================


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    filename: str
    size: int
    content_type: str
    org_id: str
    uploaded_by: str
    download_url: str | None = None


# ============================================================================
# Registry abstraction
# ============================================================================


@runtime_checkable
class FileRegistryProtocol(Protocol):

    async def register(
        self,
        meta: FileMetadata,
    ) -> FileMetadata:
        ...

    async def get(
        self,
        file_id: str,
    ) -> FileMetadata | None:
        ...

    async def list_for_org(
        self,
        org_id: str,
    ) -> list[FileMetadata]:
        ...

    async def delete(
        self,
        file_id: str,
    ) -> bool:
        ...


# ============================================================================
# In-memory registry
# ============================================================================


class FileRegistry:
    """
    Development/test metadata registry.

    Production should replace this with a PostgreSQL-backed repository.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, FileMetadata] = {}
        self._by_key: dict[str, FileMetadata] = {}

    async def register(
        self,
        meta: FileMetadata,
    ) -> FileMetadata:
        if meta.file_id in self._by_id:
            raise ValueError(
                f"file already exists: {meta.file_id}"
            )

        if meta.key in self._by_key:
            raise ValueError(
                f"object key already exists: {meta.key}"
            )

        self._by_id[meta.file_id] = meta
        self._by_key[meta.key] = meta

        return meta

    async def get(
        self,
        file_id: str,
    ) -> FileMetadata | None:
        return self._by_id.get(file_id)

    async def list_for_org(
        self,
        org_id: str,
    ) -> list[FileMetadata]:
        return [
            meta
            for meta in self._by_id.values()
            if meta.org_id == org_id
        ]

    async def delete(
        self,
        file_id: str,
    ) -> bool:
        meta = self._by_id.pop(
            file_id,
            None,
        )

        if meta is None:
            return False

        self._by_key.pop(
            meta.key,
            None,
        )

        return True


# ============================================================================
# Dependency state
# ============================================================================


_registry = FileRegistry()

_store: ObjectStore = LocalObjectStore()


def set_object_store(
    store: ObjectStore,
) -> None:
    """
    Replace the process-wide object store.

    Normally called during application startup.
    """
    global _store
    _store = store


def get_store() -> ObjectStore:
    return _store


def set_file_registry(
    registry: FileRegistryProtocol,
) -> None:
    """
    Replace the metadata registry.

    Production can inject a PostgreSQL implementation.
    """
    global _registry
    _registry = registry  # type: ignore[assignment]


def get_registry() -> FileRegistryProtocol:
    return _registry


# ============================================================================
# Authentication / authorization helpers
# ============================================================================


def _require_tenant(
    principal: Principal,
) -> str:
    """
    Require an authenticated principal with an organization scope.

    org_id is deliberately obtained from the authenticated context rather
    than from request input.
    """
    if principal.is_anonymous:
        raise Problem(
            title="Not Authenticated",
            status_code=401,
            detail="authentication required",
        )

    if not principal.org_id:
        raise Problem(
            title="No Active Organization",
            status_code=403,
            detail="an active organization is required",
        )

    return principal.org_id


def _require_permission(
    principal: Principal,
    permission: str,
) -> None:
    """
    Delegate permission enforcement to the existing authorization system.
    """
    from {{cookiecutter.project_name}}.identity.permissions import (
        has_permission,
    )

    if not has_permission(
        principal,
        permission,
    ):
        raise Problem(
            title="Insufficient Permissions",
            status_code=403,
            detail=f"requires '{permission}'",
        )


def _to_file_out(
    meta: FileMetadata,
    *,
    download_url: str | None = None,
) -> FileOut:
    return FileOut(
        file_id=meta.file_id,
        filename=meta.filename,
        size=meta.size,
        content_type=meta.content_type,
        org_id=meta.org_id,
        uploaded_by=meta.uploaded_by,
        download_url=download_url,
    )


# ============================================================================
# Router
# ============================================================================


def build_files_router(
    *,
    prefix: str = "/api/files",
    tags: list[str] | None = None,
    current_user_dep: Any,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
) -> APIRouter:
    """
    Build the files API.

    current_user_dep must resolve to Principal.

    Example:

        build_files_router(
            current_user_dep=CurrentUser,
        )
    """

    if current_user_dep is None:
        raise ValueError(
            "current_user_dep is required; "
            "files must never run without authentication"
        )

    if max_upload_bytes <= 0:
        raise ValueError(
            "max_upload_bytes must be positive"
        )

    router = APIRouter(
        prefix=prefix,
        tags=tags or ["files"],
    )

    # ------------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------------

    @router.post(
        "",
        response_model=FileOut,
        status_code=201,
    )
    async def upload_file(
        file: UploadFile = FileUpload(...),
        principal: Principal = Depends(
            current_user_dep
        ),
    ) -> FileOut:
        """
        Upload a file to the caller's active organization.
        """

        org_id = _require_tenant(principal)

        _require_permission(
            principal,
            "files.write",
        )

        filename = (
            file.filename
            or "upload.bin"
        )

        content_type = (
            file.content_type
            or DEFAULT_CONTENT_TYPE
        )

        # Never use a client-supplied org_id.
        key = new_file_key(
            org_id,
            filename,
        )

        # --------------------------------------------------------------------
        # Bounded read.
        #
        # UploadFile.read() without a limit allows the request body to become
        # arbitrarily large before we reject it.
        # --------------------------------------------------------------------

        data = bytearray()

        try:
            while True:
                chunk = await file.read(
                    min(
                        1024 * 1024,
                        max_upload_bytes + 1 - len(data),
                    )
                )

                if not chunk:
                    break

                data.extend(chunk)

                if len(data) > max_upload_bytes:
                    raise Problem(
                        title="Payload Too Large",
                        status_code=413,
                        detail=(
                            f"file exceeds "
                            f"{max_upload_bytes} bytes"
                        ),
                    )

            raw_data = bytes(data)

            # ----------------------------------------------------------------
            # Store object first.
            # ----------------------------------------------------------------

            await get_store().put(
                key,
                raw_data,
                content_type=content_type,
            )

            # ----------------------------------------------------------------
            # Register metadata only after successful object upload.
            # ----------------------------------------------------------------

            import time

            meta = FileMetadata(
                file_id=new_id("file"),
                key=key,
                filename=filename,
                size=len(raw_data),
                content_type=content_type,
                org_id=org_id,
                uploaded_by=principal.user_id,
                created_at=time.time(),
            )

            try:
                await get_registry().register(
                    meta
                )
            except Exception:
                # Compensating action: metadata failed, therefore remove
                # the orphaned object.
                try:
                    await get_store().delete(key)
                except Exception:
                    pass

                raise

        finally:
            await file.close()

        download_url: str | None = None

        try:
            download_url = (
                await get_store().presigned_get_url(
                    key,
                    ttl_s=ALLOWED_DOWNLOAD_TTL_S,
                )
            )
        except NotImplementedError:
            # Local storage may not support real presigned URLs.
            pass

        return _to_file_out(
            meta,
            download_url=download_url,
        )

    # ------------------------------------------------------------------------
    # List organization files
    #
    # Registered BEFORE /{file_id} so FastAPI does not capture "org" as an id.
    # ------------------------------------------------------------------------

    @router.get(
        "/org",
        response_model=list[FileOut],
    )
    async def list_org_files(
        principal: Principal = Depends(
            current_user_dep
        ),
    ) -> list[FileOut]:
        """
        List files belonging to the authenticated organization.

        The organization is derived from Principal.
        """

        org_id = _require_tenant(principal)

        _require_permission(
            principal,
            "files.read",
        )

        items = await get_registry().list_for_org(
            org_id
        )

        return [
            _to_file_out(meta)
            for meta in items
        ]

    # ------------------------------------------------------------------------
    # Get metadata + download URL
    # ------------------------------------------------------------------------

    @router.get(
        "/{file_id}",
        response_model=FileOut,
    )
    async def get_file(
        file_id: str,
        principal: Principal = Depends(
            current_user_dep
        ),
    ) -> FileOut:
        """
        Return metadata and a short-lived download URL.
        """

        org_id = _require_tenant(principal)

        _require_permission(
            principal,
            "files.read",
        )

        meta = await get_registry().get(
            file_id
        )

        if meta is None:
            raise Problem(
                title="Not Found",
                status_code=404,
                detail="file not found",
            )

        # Tenant ownership is mandatory.
        if meta.org_id != org_id:
            raise Problem(
                title="Forbidden",
                status_code=403,
                detail="cross-organization access denied",
            )

        url = await get_store().presigned_get_url(
            meta.key,
            ttl_s=ALLOWED_DOWNLOAD_TTL_S,
        )

        return _to_file_out(
            meta,
            download_url=url,
        )

    # ------------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------------

    @router.delete(
        "/{file_id}",
        status_code=204,
    )
    async def delete_file(
        file_id: str,
        principal: Principal = Depends(
            current_user_dep
        ),
    ) -> None:
        """
        Delete an object after verifying tenant ownership.
        """

        org_id = _require_tenant(principal)

        _require_permission(
            principal,
            "files.delete",
        )

        meta = await get_registry().get(
            file_id
        )

        if meta is None:
            raise Problem(
                title="Not Found",
                status_code=404,
                detail="file not found",
            )

        if meta.org_id != org_id:
            raise Problem(
                title="Forbidden",
                status_code=403,
                detail="cross-organization access denied",
            )

        # Delete object first.
        await get_store().delete(
            meta.key
        )

        # Then delete metadata.
        await get_registry().delete(
            file_id
        )

    return router


__all__ = [
    "MAX_UPLOAD_BYTES",
    "DEFAULT_CONTENT_TYPE",
    "ALLOWED_DOWNLOAD_TTL_S",
    "FileMetadata",
    "FileOut",
    "FileRegistryProtocol",
    "FileRegistry",
    "set_object_store",
    "get_store",
    "set_file_registry",
    "get_registry",
    "build_files_router",
]
