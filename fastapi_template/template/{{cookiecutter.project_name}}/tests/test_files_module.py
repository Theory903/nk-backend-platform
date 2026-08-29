"""Tests for platform.files: ObjectStore contract + files HTTP module."""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from {{cookiecutter.project_name}}.core.errors import register_problem_handlers
from {{cookiecutter.project_name}}.identity.principal import Principal
from {{cookiecutter.project_name}}.platform.files import (
    LocalObjectStore,
    get_object_store,
    new_file_key,
    validate_object_key,
)
from {{cookiecutter.project_name}}.platform.files.router import (
    FileRegistry,
    build_files_router,
    set_file_registry,
    set_object_store,
)


@pytest.fixture
def store(tmp_path):
    return LocalObjectStore(root=tmp_path / "files")


class TestObjectStoreContract:
    async def test_put_get_roundtrip(self, store) -> None:
        key = await store.put("org1/a.txt", b"hello", content_type="text/plain")
        assert key == "org1/a.txt"
        assert await store.get("org1/a.txt") == b"hello"

    async def test_get_missing_returns_none(self, store) -> None:
        assert await store.get("nope/missing.bin") is None

    async def test_delete_removes(self, store) -> None:
        await store.put("x/y.bin", b"data")
        assert await store.delete("x/y.bin") is True
        assert await store.get("x/y.bin") is None

    async def test_delete_missing_returns_false(self, store) -> None:
        assert await store.delete("never/existed") is False

    async def test_validate_object_key_rejects_dotdot(self) -> None:
        with pytest.raises(ValueError, match="unsafe object key"):
            validate_object_key("../../etc/passwd")
        with pytest.raises(ValueError, match="unsafe object key"):
            validate_object_key("org/../secret")

    async def test_key_escape_blocked(self, store) -> None:
        with pytest.raises(ValueError, match="unsafe object key"):
            await store.put("../../etc/passwd", b"evil")

    async def test_presigned_get_local_shape(self, store) -> None:
        url = await store.presigned_get_url("k.txt", ttl_s=60)
        assert "ttl=60" in url

    async def test_concurrent_unique_tmp_smoke(self, store) -> None:
        async def _write(i: int) -> str:
            return await store.put(f"org/c{i}.bin", f"payload-{i}".encode())

        keys = await asyncio.gather(*[_write(i) for i in range(8)])
        assert len(set(keys)) == 8
        for i, key in enumerate(keys):
            assert await store.get(key) == f"payload-{i}".encode()


class TestFactory:
    def test_local_backend(self) -> None:
        store = get_object_store("local")
        assert isinstance(store, LocalObjectStore)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown files backend"):
            get_object_store("gcs")

    def test_s3_backend_requires_boto3(self) -> None:
        try:
            import boto3  # noqa: F401

            has_boto3 = True
        except ModuleNotFoundError:
            has_boto3 = False
        if has_boto3:
            pytest.skip("boto3 installed; cannot test the missing-dep path")
        with pytest.raises(RuntimeError, match="requires boto3"):
            get_object_store("s3", bucket="b")


class TestNewFileKey:
    def test_org_scoped_with_extension(self) -> None:
        key = new_file_key("org_9", "report.pdf")
        assert key.startswith("org_9/")
        assert key.endswith(".pdf")

    def test_unique_keys(self) -> None:
        k1 = new_file_key("o", "a.png")
        k2 = new_file_key("o", "a.png")
        assert k1 != k2


def _principal(
    *,
    user_id: str = "user_1",
    org_id: str | None = "org_1",
    roles: frozenset[str] | None = None,
) -> Principal:
    return Principal(
        user_id=user_id,
        org_id=org_id,
        roles=roles or frozenset({"owner"}),
    )


@pytest.fixture
def client(tmp_path):
    set_object_store(LocalObjectStore(root=tmp_path / "uploads"))
    set_file_registry(FileRegistry())

    app = FastAPI()
    register_problem_handlers(app)

    async def current_user() -> Principal:
        return _principal()

    router = build_files_router(
        prefix="/api/files",
        current_user_dep=current_user,
        max_upload_bytes=1024,
    )
    app.include_router(router)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


def _make_client(
    tmp_path,
    *,
    principal: Principal,
    max_upload_bytes: int = 1024,
) -> AsyncClient:
    set_object_store(LocalObjectStore(root=tmp_path / "uploads"))
    set_file_registry(FileRegistry())

    app = FastAPI()
    register_problem_handlers(app)

    async def current_user() -> Principal:
        return principal

    app.include_router(
        build_files_router(
            prefix="/api/files",
            current_user_dep=current_user,
            max_upload_bytes=max_upload_bytes,
        )
    )
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.anyio
class TestFilesApi:
    async def test_upload_uses_principal_org_id_not_form(self, client) -> None:
        resp = await client.post(
            "/api/files",
            files={
                "file": (
                    "notes.txt",
                    io.BytesIO(b"hello world"),
                    "text/plain",
                )
            },
            data={"org_id": "attacker_org"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "notes.txt"
        assert body["size"] == 11
        assert body["org_id"] == "org_1"
        assert "key" not in body

        got = await client.get(f"/api/files/{body['file_id']}")
        assert got.status_code == 200
        assert got.json()["download_url"]
        assert "key" not in got.json()

    async def test_cross_org_get_and_delete_denied(self, tmp_path) -> None:
        set_object_store(LocalObjectStore(root=tmp_path / "shared"))
        set_file_registry(FileRegistry())

        app = FastAPI()
        register_problem_handlers(app)
        state = {"principal": _principal(org_id="org_A")}

        async def current_user() -> Principal:
            return state["principal"]

        app.include_router(
            build_files_router(
                prefix="/api/files",
                current_user_dep=current_user,
            )
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as http:
            up = await http.post(
                "/api/files",
                files={
                    "file": (
                        "f.bin",
                        io.BytesIO(b"x"),
                        "application/octet-stream",
                    )
                },
            )
            assert up.status_code == 201
            file_id = up.json()["file_id"]

            state["principal"] = _principal(user_id="user_b", org_id="org_B")
            denied = await http.get(f"/api/files/{file_id}")
            assert denied.status_code == 403

            denied_del = await http.delete(f"/api/files/{file_id}")
            assert denied_del.status_code == 403

    async def test_anonymous_returns_401(self, tmp_path) -> None:
        async with _make_client(
            tmp_path,
            principal=Principal(user_id=""),
        ) as http:
            resp = await http.post(
                "/api/files",
                files={
                    "file": (
                        "a.txt",
                        io.BytesIO(b"x"),
                        "text/plain",
                    )
                },
            )
            assert resp.status_code == 401

    async def test_oversize_returns_413(self, client) -> None:
        payload = b"x" * 2048
        resp = await client.post(
            "/api/files",
            files={
                "file": (
                    "big.bin",
                    io.BytesIO(payload),
                    "application/octet-stream",
                )
            },
        )
        assert resp.status_code == 413

    async def test_delete_removes_metadata_and_object(self, client) -> None:
        up = await client.post(
            "/api/files",
            files={
                "file": (
                    "d.txt",
                    io.BytesIO(b"z"),
                    "text/plain",
                )
            },
        )
        file_id = up.json()["file_id"]
        deleted = await client.delete(f"/api/files/{file_id}")
        assert deleted.status_code == 204
        missing = await client.get(f"/api/files/{file_id}")
        assert missing.status_code == 404

    async def test_list_org_no_path_org_id(self, client) -> None:
        for i in range(3):
            await client.post(
                "/api/files",
                files={
                    "file": (
                        f"f{i}.txt",
                        io.BytesIO(b"v"),
                        "text/plain",
                    )
                },
            )
        listed = await client.get("/api/files/org")
        assert listed.status_code == 200
        assert len(listed.json()) >= 3
        # Path org_id must not be a valid list route.
        wrong = await client.get("/api/files/org/org_1")
        assert wrong.status_code == 404

    async def test_unknown_file_404(self, client) -> None:
        resp = await client.get("/api/files/file_nope")
        assert resp.status_code == 404
