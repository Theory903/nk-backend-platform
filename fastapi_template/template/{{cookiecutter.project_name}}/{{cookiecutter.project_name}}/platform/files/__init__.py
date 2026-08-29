"""
Object storage abstraction.

Backends:

    LocalObjectStore
        Development / tests only.

    S3ObjectStore
        Production S3 / MinIO / S3-compatible storage.

The application talks only to ObjectStore.

Object keys are opaque identifiers. Tenant isolation is enforced by requiring
an organization-scoped key for application-created objects.

Important:
    - Never store secrets in object metadata.
    - Never trust client-provided object keys directly.
    - Presigned URLs must have short bounded TTLs.
    - Large files should use multipart/direct-to-object-storage uploads.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, runtime_checkable

from {{cookiecutter.project_name}}.core.identifiers import new_id


# ============================================================================
# Models
# ============================================================================


@dataclass(frozen=True)
class ObjectMetadata:
    """
    Metadata returned for an object.
    """

    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None
    version_id: str | None = None
    checksum_sha256: str | None = None


# ============================================================================
# Interface
# ============================================================================


@runtime_checkable
class ObjectStore(Protocol):
    """
    Common object-storage interface.

    Implementations may use local disk, S3, MinIO, etc.
    """

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> str:
        ...

    async def get(
        self,
        key: str,
    ) -> bytes | None:
        ...

    async def head(
        self,
        key: str,
    ) -> ObjectMetadata | None:
        ...

    async def delete(
        self,
        key: str,
    ) -> bool:
        ...

    async def exists(
        self,
        key: str,
    ) -> bool:
        ...

    async def presigned_put_url(
        self,
        key: str,
        *,
        ttl_s: int = 900,
        content_type: str | None = None,
    ) -> str:
        ...

    async def presigned_get_url(
        self,
        key: str,
        *,
        ttl_s: int = 900,
    ) -> str:
        ...


# ============================================================================
# Validation
# ============================================================================


_MAX_PRESIGNED_TTL_S = 3600


def validate_object_key(key: str) -> str:
    """
    Validate an object key.

    Keys must be relative POSIX-style paths and must not escape their
    logical namespace.
    """
    if not isinstance(key, str):
        raise TypeError("object key must be a string")

    key = key.strip()

    if not key:
        raise ValueError("object key cannot be empty")

    if len(key) > 1024:
        raise ValueError("object key is too long")

    if "\x00" in key:
        raise ValueError("object key contains NUL byte")

    if key.startswith("/"):
        raise ValueError("absolute object keys are not allowed")

    path = PurePosixPath(key)

    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(
            f"unsafe object key: {key}"
        )

    return str(path)


def validate_presigned_ttl(ttl_s: int) -> int:
    """
    Restrict presigned URL lifetime.
    """
    if not isinstance(ttl_s, int):
        raise TypeError("ttl_s must be an integer")

    if ttl_s <= 0:
        raise ValueError("ttl_s must be positive")

    if ttl_s > _MAX_PRESIGNED_TTL_S:
        raise ValueError(
            f"ttl_s cannot exceed {_MAX_PRESIGNED_TTL_S}s"
        )

    return ttl_s


def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ============================================================================
# Local store
# ============================================================================


class LocalObjectStore:
    """
    Filesystem-backed object store.

    Intended for development and tests.

    Do not use this as the production multi-node storage backend.
    """

    def __init__(
        self,
        root: str | Path = ".data/files",
        *,
        url_ttl_s: int = 900,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.url_ttl_s = validate_presigned_ttl(
            url_ttl_s
        )

    def _resolve(
        self,
        key: str,
    ) -> Path:
        key = validate_object_key(key)

        target = (
            self.root / Path(*PurePosixPath(key).parts)
        ).resolve()

        if not target.is_relative_to(self.root):
            raise PermissionError(
                f"object key escapes storage root: {key}"
            )

        return target

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> str:
        """
        Atomically write an object.

        A unique temporary file prevents concurrent writers from colliding.
        """
        target = self._resolve(key)

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        def _write() -> None:
            tmp = target.with_name(
                f".{target.name}.{secrets.token_hex(8)}.tmp"
            )

            try:
                tmp.write_bytes(data)
                tmp.replace(target)
            finally:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass

        await asyncio.to_thread(_write)

        return key

    async def get(
        self,
        key: str,
    ) -> bytes | None:
        target = self._resolve(key)

        def _read() -> bytes | None:
            if not target.is_file():
                return None

            return target.read_bytes()

        return await asyncio.to_thread(_read)

    async def head(
        self,
        key: str,
    ) -> ObjectMetadata | None:
        target = self._resolve(key)

        def _head() -> ObjectMetadata | None:
            if not target.is_file():
                return None

            data = target.read_bytes()

            return ObjectMetadata(
                key=key,
                size=len(data),
                checksum_sha256=calculate_sha256(data),
            )

        return await asyncio.to_thread(_head)

    async def exists(
        self,
        key: str,
    ) -> bool:
        target = self._resolve(key)

        return await asyncio.to_thread(
            target.is_file
        )

    async def delete(
        self,
        key: str,
    ) -> bool:
        target = self._resolve(key)

        def _delete() -> bool:
            if not target.is_file():
                return False

            target.unlink()
            return True

        return await asyncio.to_thread(_delete)

    async def presigned_put_url(
        self,
        key: str,
        *,
        ttl_s: int = 900,
        content_type: str | None = None,
    ) -> str:
        raise NotImplementedError(
            "local storage does not support direct presigned uploads"
        )

    async def presigned_get_url(
        self,
        key: str,
        *,
        ttl_s: int = 900,
    ) -> str:
        key = validate_object_key(key)
        ttl = validate_presigned_ttl(ttl_s)

        return (
            f"/files/local/{key}"
            f"?ttl={ttl}"
        )


# ============================================================================
# S3 / MinIO
# ============================================================================


class S3ObjectStore:
    """
    S3-compatible object store.

    Works with AWS S3 and S3-compatible systems such as MinIO.
    """

    def __init__(
        self,
        bucket: str,
        *,
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        url_ttl_s: int = 900,
    ) -> None:
        try:
            import boto3
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "S3ObjectStore requires boto3"
            ) from exc

        if not bucket.strip():
            raise ValueError(
                "S3 bucket cannot be empty"
            )

        client_kwargs: dict[str, Any] = {}

        if region:
            client_kwargs["region_name"] = region

        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        if access_key_id:
            client_kwargs["aws_access_key_id"] = access_key_id

        if secret_access_key:
            client_kwargs["aws_secret_access_key"] = (
                secret_access_key
            )

        self._client = boto3.client(
            "s3",
            **client_kwargs,
        )

        self.bucket = bucket
        self.url_ttl_s = validate_presigned_ttl(
            url_ttl_s
        )

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> str:
        key = validate_object_key(key)

        extra: dict[str, Any] = {}

        if content_type:
            extra["ContentType"] = content_type

        checksum = calculate_sha256(data)

        extra["Metadata"] = {
            "sha256": checksum,
        }

        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **extra,
        )

        return key

    async def get(
        self,
        key: str,
    ) -> bytes | None:
        key = validate_object_key(key)

        def _get() -> bytes | None:
            try:
                response = self._client.get_object(
                    Bucket=self.bucket,
                    Key=key,
                )
            except self._client.exceptions.NoSuchKey:
                return None

            return response["Body"].read()

        return await asyncio.to_thread(_get)

    async def head(
        self,
        key: str,
    ) -> ObjectMetadata | None:
        key = validate_object_key(key)

        def _head() -> ObjectMetadata | None:
            try:
                response = self._client.head_object(
                    Bucket=self.bucket,
                    Key=key,
                )
            except Exception as exc:
                error = getattr(exc, "response", {})
                status = (
                    error.get("ResponseMetadata", {})
                    .get("HTTPStatusCode")
                )

                if status == 404:
                    return None

                raise

            metadata = response.get(
                "Metadata",
                {},
            )

            return ObjectMetadata(
                key=key,
                size=int(
                    response.get(
                        "ContentLength",
                        0,
                    )
                ),
                content_type=response.get(
                    "ContentType"
                ),
                etag=response.get("ETag"),
                version_id=response.get(
                    "VersionId"
                ),
                checksum_sha256=metadata.get(
                    "sha256"
                ),
            )

        return await asyncio.to_thread(_head)

    async def exists(
        self,
        key: str,
    ) -> bool:
        return (
            await self.head(key)
        ) is not None

    async def delete(
        self,
        key: str,
    ) -> bool:
        key = validate_object_key(key)

        existed = await self.exists(key)

        if not existed:
            return False

        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self.bucket,
            Key=key,
        )

        return True

    async def presigned_put_url(
        self,
        key: str,
        *,
        ttl_s: int = 900,
        content_type: str | None = None,
    ) -> str:
        key = validate_object_key(key)
        ttl = validate_presigned_ttl(ttl_s)

        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
        }

        if content_type:
            params["ContentType"] = content_type

        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=ttl,
        )

    async def presigned_get_url(
        self,
        key: str,
        *,
        ttl_s: int = 900,
    ) -> str:
        key = validate_object_key(key)
        ttl = validate_presigned_ttl(ttl_s)

        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
            },
            ExpiresIn=ttl,
        )


# ============================================================================
# Factory
# ============================================================================


def get_object_store(
    backend: str = "local",
    **kwargs: Any,
) -> ObjectStore:
    """
    Construct the configured object-store implementation.
    """
    normalized = backend.strip().lower()

    if normalized == "local":
        return LocalObjectStore(**kwargs)

    if normalized in {
        "s3",
        "minio",
    }:
        return S3ObjectStore(**kwargs)

    raise ValueError(
        f"unknown files backend '{backend}'"
    )


# ============================================================================
# Application object-key generation
# ============================================================================


def new_file_key(
    org_id: str,
    filename: str,
) -> str:
    """
    Create a tenant-scoped, collision-resistant object key.

    Only the extension from the supplied filename is retained.

    Example:

        org_123/report.pdf

    becomes:

        org_123/file_xxxxxxxxx.pdf
    """
    if not org_id:
        raise ValueError(
            "org_id is required"
        )

    if not filename:
        raise ValueError(
            "filename is required"
        )

    # Only preserve a safe extension.
    suffix = Path(filename).suffix.lower()

    if len(suffix) > 32:
        suffix = ""

    if suffix and not suffix.startswith("."):
        suffix = ""

    safe_org_id = validate_object_key(
        org_id
    )

    return (
        f"{safe_org_id}/"
        f"{new_id('file')}"
        f"{suffix}"
    )


__all__ = [
    "ObjectMetadata",
    "ObjectStore",
    "validate_object_key",
    "validate_presigned_ttl",
    "calculate_sha256",
    "LocalObjectStore",
    "S3ObjectStore",
    "get_object_store",
    "new_file_key",
]