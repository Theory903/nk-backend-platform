"""Tests for convention-based business router discovery."""

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI

from {{cookiecutter.project_name}}.core.module_discovery import (
    ModuleDiscoveryError,
    discover_business_routers,
    include_business_routers,
)


def _write_router(root: Path, module: str, prefix: str) -> None:
    parts = module.split(".")
    package_dir = root.joinpath(*parts[:-1])
    package_dir.mkdir(parents=True)
    for index in range(1, len(parts)):
        init_file = root.joinpath(*parts[:index], "__init__.py")
        init_file.write_text("")
    (package_dir / f"{parts[-1]}.py").write_text(
        f'''from fastapi import APIRouter

router = APIRouter(prefix="{prefix}")


@router.get("/")
async def read_item() -> dict[str, str]:
    return dict(status="ok")
''',
    )


def test_discovers_and_mounts_business_routers(tmp_path: Path) -> None:
    _write_router(
        tmp_path,
        "business.modules.crm.leads.router",
        "/leads",
    )
    _write_router(
        tmp_path,
        "business.modules.crm.accounts.router",
        "/accounts",
    )

    discovered = discover_business_routers(tmp_path)
    assert [item.module_name for item in discovered] == [
        "business.modules.crm.accounts.router",
        "business.modules.crm.leads.router",
    ]
    assert [item.mount_prefix for item in discovered] == [
        "/v1/crm",
        "/v1/crm",
    ]
    assert [item.route_prefix for item in discovered] == [
        "/v1/crm/accounts",
        "/v1/crm/leads",
    ]

    api_router = APIRouter()
    include_business_routers(api_router, root=tmp_path)
    include_business_routers(api_router, root=tmp_path)
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    assert set(app.openapi()["paths"]) == {
        "/api/v1/crm/accounts/",
        "/api/v1/crm/leads/",
    }


def test_rejects_duplicate_business_route_prefix(tmp_path: Path) -> None:
    _write_router(
        tmp_path,
        "business.modules.crm.leads.router",
        "/records",
    )
    _write_router(
        tmp_path,
        "business.modules.crm.contacts.router",
        "/records",
    )

    with pytest.raises(ModuleDiscoveryError, match="duplicate business route"):
        discover_business_routers(tmp_path)


def test_discovery_isolated_between_project_roots(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _write_router(
        first_root,
        "business.modules.crm.leads.router",
        "/first",
    )
    _write_router(
        second_root,
        "business.modules.crm.leads.router",
        "/second",
    )

    first = discover_business_routers(first_root)
    second = discover_business_routers(second_root)

    assert first[0].route_prefix == "/v1/crm/first"
    assert second[0].route_prefix == "/v1/crm/second"
